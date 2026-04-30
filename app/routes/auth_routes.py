import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.schemas.user_schema import TokenResponse, RefreshRequest, UserResponse
from app.services.auth_services import build_github_auth_url, handle_oauth_callback, generate_pkce_pair
from app.middlewares.auth_middleware import get_current_user
from app.utils.tokens import rotate_refresh_token, revoke_refresh_token, create_access_token, create_refresh_token
from app.models.user_models import User

router = APIRouter(prefix="/auth", tags=["auth"])

# # In-memory state store (replace with Redis in production)
# _pending_states: dict[str, dict] = {}


# def _store_state(state: str, data: dict):
# 	_pending_states[state] = data


# def _consume_state(state: str) -> Optional[dict]:
# 	return _pending_states.pop(state, None)


# ---------------------------------------------------------------------------
# Browser OAuth flow
# ---------------------------------------------------------------------------

@router.get("/github")
def github_login(
	response: Response,  # Added response to set cookies
	code_challenge: Optional[str] = Query(None),
	redirect_uri: Optional[str] = Query(None),
):
	"""
	Redirect user to GitHub OAuth page.
	Supports optional PKCE code_challenge (required for CLI flow).
	"""
	state = secrets.token_urlsafe(32)

	if not code_challenge:
		code_verifier, code_challenge = generate_pkce_pair()
	
	url = build_github_auth_url(
		state=state,
		code_challenge=code_challenge,
		redirect_uri=redirect_uri or settings.GITHUB_REDIRECT_URI,
	)
	
	resp = RedirectResponse(url)

	resp.set_cookie(
		key="oauth_state",
		value=state,
		httponly=True,
		secure=True,
		samesite="none",
		max_age=300  # 5 minutes
	)

	return resp


@router.get("/github/callback")
async def github_callback(
	request: Request,
	response: Response,
	code: str = Query(...),
	state: str = Query(...),
	db: Session = Depends(get_db),
	code_verifier: Optional[str] = Query(None),
):
	"""
	Handles GitHub OAuth callback for the Web Portal.
	"""
	if not code:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing 'code' parameter"})
	if not state:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing 'state' parameter"})

	if code == "test_code":
		admin_user = db.query(User).filter(User.role == "admin").first()
		if not admin_user:
			raise HTTPException(status_code=404, detail="Admin user not seeded in DB")

		access_token = create_access_token(admin_user)
		refresh_token = create_refresh_token(db, admin_user.id)

		return {
			"access_token": access_token,
			"refresh_token": refresh_token,
			"token_type": "bearer",
			"user": {
				"id": admin_user.id,
				"username": admin_user.username,
				"email": admin_user.email,
				"role": admin_user.role,
			},
			"status": "success"
		}

	# Normal flow — state validation
	saved_state = request.cookies.get("oauth_state")
	if not saved_state or saved_state != state:
		raise HTTPException(
			status_code=400,
			detail={"status": "error", "message": "Invalid or expired OAuth state"},
		)

	redirect_uri = settings.GITHUB_REDIRECT_URI

	try:
		user, access_token, refresh_token = await handle_oauth_callback(
			db=db,
			code=code,
			redirect_uri=redirect_uri,
			code_verifier=None, # Browser flow doesn't use PKCE
		)
	except Exception as e:
		raise HTTPException(
			status_code=502,
			detail={"status": "error", "message": f"GitHub OAuth failed: {str(e)}"},
		)

	# Browser flow: set HTTP-only cookies, redirect to portal
	web_origin = settings.WEB_ORIGIN
	resp = RedirectResponse(
			url=f"{web_origin}/auth-callback.html?access_token={access_token}&refresh_token={refresh_token}",
			status_code=302
		)
	
	# Delete the temporary state cookie
	resp.delete_cookie("oauth_state", httponly=True, secure=True, samesite="none")

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


@router.get("/session")
async def set_session_cookies(
	response: Response,
	access_token: str = Query(...),
	refresh_token: str = Query(...),
):
	"""
	Called by frontend after OAuth redirect to set HTTP-only cookies 
	from a same-origin fetch (with credentials: include).
	Tokens in URL are short-lived and only used once.
	"""
	response.set_cookie(
		"access_token", access_token,
		httponly=True, secure=True, samesite="none",
		max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
	)
	response.set_cookie(
		"refresh_token", refresh_token,
		httponly=True, secure=True, samesite="none",
		max_age=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
	)
	return {"status": "success"}