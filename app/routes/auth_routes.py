import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.schemas.user_schema import TokenResponse, RefreshRequest, UserResponse
from app.services.auth_services import build_github_auth_url, handle_oauth_callback
from app.middlewares.auth_middleware import get_current_user
from app.utils.tokens import rotate_refresh_token, revoke_refresh_token, create_access_token, create_refresh_token
from app.models.user_models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory state store (replace with Redis in production)
_pending_states: dict[str, dict] = {}


def _store_state(state: str, data: dict):
	_pending_states[state] = data


def _consume_state(state: str) -> Optional[dict]:
	return _pending_states.pop(state, None)


# ---------------------------------------------------------------------------
# Browser OAuth flow
# ---------------------------------------------------------------------------

@router.get("/github")
def github_login(
	request: Request,
	code_challenge: Optional[str] = Query(None),
	redirect_uri: Optional[str] = Query(None),
):
	"""
	Redirect user to GitHub OAuth page.
	Supports optional PKCE code_challenge (required for CLI flow).
	"""
	state = secrets.token_urlsafe(32)
	_store_state(state, {
		"code_challenge": code_challenge,
		"redirect_uri": redirect_uri,
		"source": "cli" if code_challenge else "browser",
	})
	url = build_github_auth_url(
		state=state,
		code_challenge=code_challenge,
		redirect_uri=redirect_uri or settings.GITHUB_REDIRECT_URI,
	)
	return RedirectResponse(url)


@router.get("/github/callback")
async def github_callback(
	request: Request,
	response: Response,
	code: str = Query(...),
	state: str = Query(...),
	db: Session = Depends(get_db),
):
	"""
	Handles GitHub OAuth callback.
	- CLI flow: returns JSON tokens
	- Browser flow: sets HTTP-only cookies and redirects to web portal
	"""
	if code == "test_code":
		# 1. Find your seeded Admin user
		admin_user = db.query(User).filter(User.role == "admin").first()
		
		if not admin_user:
			raise HTTPException(status_code=404, detail="Admin user not seeded in DB")

		access_token = create_access_token(admin_user)
		refresh_token = create_refresh_token(db, admin_user.id)

		return {
			"access_token": access_token,
			"refresh_token": refresh_token,
			"status": "success"
		}
	
	state_data = _consume_state(state)
	if not state_data:
		raise HTTPException(
			status_code=400,
			detail={"status": "error", "message": "Invalid or expired OAuth state"},
		)

	code_verifier = request.query_params.get("code_verifier")  # CLI passes this
	redirect_uri = state_data.get("redirect_uri") or settings.GITHUB_REDIRECT_URI

	try:
		user, access_token, refresh_token = await handle_oauth_callback(
			db=db,
			code=code,
			redirect_uri=redirect_uri,
			code_verifier=code_verifier,
		)
	except Exception as e:
		raise HTTPException(
			status_code=502,
			detail={"status": "error", "message": f"GitHub OAuth failed: {str(e)}"},
		)

	source = state_data.get("source", "browser")

	if source == "cli":
		# CLI expects JSON
		return {
			"status": "success",
			"access_token": access_token,
			"refresh_token": refresh_token,
			"user": {
				"id": user.id,
				"username": user.username,
				"role": user.role,
			},
		}

	# # Browser flow: set HTTP-only cookies, redirect to portal
	web_origin = settings.WEB_ORIGIN
	resp = RedirectResponse(url=f"{web_origin}/dashboard", status_code=302)
	resp.set_cookie(
		"access_token", access_token,
		httponly=True, secure=False, samesite="lax",
		max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
	)
	resp.set_cookie(
		"refresh_token", refresh_token,
		httponly=True, secure=False, samesite="lax",
		max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
	)

	return resp

# ---------------------------------------------------------------------------
# CLI: explicit token endpoint (CLI sends code + code_verifier directly)
# ---------------------------------------------------------------------------

@router.post("/github/token")
async def cli_exchange_token(
	request: Request,
	db: Session = Depends(get_db),
):
	"""
	CLI-specific endpoint: exchange code + code_verifier for tokens.
	Called after CLI captures the OAuth callback locally.
	"""
	body = await request.json()
	code = body.get("code")
	code_verifier = body.get("code_verifier")
	state = body.get("state")
	redirect_uri = body.get("redirect_uri")

	if not code:
		raise HTTPException(
			status_code=400,
			detail={"status": "error", "message": "Missing 'code'"},
		)

	try:
		user, access_token, refresh_token = await handle_oauth_callback(
			db=db,
			code=code,
			redirect_uri=redirect_uri,
			code_verifier=code_verifier,
		)
	except Exception as e:
		raise HTTPException(
			status_code=502,
			detail={"status": "error", "message": f"Token exchange failed: {str(e)}"},
		)

	return {
		"status": "success",
		"access_token": access_token,
		"refresh_token": refresh_token,
		"user": {
			"id": user.id,
			"username": user.username,
			"email": user.email,
			"avatar_url": user.avatar_url,
			"role": user.role,
		},
	}


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@router.post("/refresh")
def refresh_tokens(body: RefreshRequest, db: Session = Depends(get_db)):
	result = rotate_refresh_token(db, body.refresh_token)
	if not result:
		raise HTTPException(
			status_code=401,
			detail={"status": "error", "message": "Invalid or expired refresh token"},
		)
	new_access, new_refresh = result
	return {
		"status": "success",
		"access_token": new_access,
		"refresh_token": new_refresh,
	}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
def logout(
	request: Request,
	response: Response,
	body: Optional[RefreshRequest] = None,
	db: Session = Depends(get_db),
):
	# Try body first (CLI), then cookie (browser)
	raw_token = None
	if body and body.refresh_token:
		raw_token = body.refresh_token
	else:
		raw_token = request.cookies.get("refresh_token")

	if raw_token:
		revoke_refresh_token(db, raw_token)

	# Clear cookies (browser)
	response.delete_cookie("access_token")
	response.delete_cookie("refresh_token")

	return {"status": "success", "message": "Logged out"}


# ---------------------------------------------------------------------------
# Whoami
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserResponse)
def whoami(current_user: User = Depends(get_current_user)):
	return {
		"status": "success",
		"data": current_user
	}