import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.db.database import get_db
from app.schemas.user_schema import UserResponse
from app.services.auth_services import build_github_auth_url, handle_oauth_callback, generate_pkce_pair
from app.middlewares.auth_middleware import get_current_user
from app.utils.tokens import rotate_refresh_token, revoke_refresh_token, create_access_token, create_refresh_token
from app.models.user_models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github")
def github_login(
	request: Request,
	code_challenge: Optional[str] = Query(None),
	redirect_uri: Optional[str] = Query(None),
):
	"""
	Redirect user to GitHub OAuth page.
	"""
	state = secrets.token_urlsafe(32)
	is_cli = code_challenge is not None

	actual_redirect_uri = redirect_uri or settings.GITHUB_REDIRECT_URI
	code_verifier = None

	if not is_cli:
		code_verifier, code_challenge = generate_pkce_pair()


	
	url = build_github_auth_url(
		state=state,
		code_challenge=code_challenge,
		redirect_uri=actual_redirect_uri,
		is_cli=is_cli
	)
	
	resp = RedirectResponse(url)

	
	resp.headers["Access-Control-Allow-Origin"] = "*"

	resp.set_cookie("oauth_state", state, httponly=True, secure=True, samesite="none", max_age=300)
	resp.set_cookie("oauth_redirect_uri", actual_redirect_uri, httponly=True, secure=True, samesite="none", max_age=300)

	if code_verifier:
		resp.set_cookie("oauth_verifier", code_verifier, httponly=True, secure=True, samesite="none", max_age=300)

	return resp


@router.get("/github/callback")
async def github_callback(
	request: Request,
	response: Response,
	db: Session = Depends(get_db),
	code: Optional[str] = Query(None),
	state: Optional[str] = Query(None),
):
	"""
	Handles GitHub OAuth callback for the Web Portal.
	"""
	if not code:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing 'code' parameter"})
	if not state:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing 'state' parameter"})

	# Admin seeding test bypass
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

	# Validate state
	saved_state = request.cookies.get("oauth_state")
	if not saved_state or saved_state != state:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid or expired OAuth state"})
	
	actual_redirect_uri = request.cookies.get("oauth_redirect_uri") or settings.GITHUB_REDIRECT_URI

	code_verifier = request.cookies.get("oauth_verifier")

	try:
		user, access_token, refresh_token = await handle_oauth_callback(
			db=db,
			code=code,
			redirect_uri=actual_redirect_uri,
			code_verifier=code_verifier,
			is_cli=False
		)
	except Exception as e:
		print(f"OAUTH EXCHANGE FAILED: {e}")
		raise HTTPException(status_code=502, detail={"status": "error", "message": f"GitHub OAuth failed: {str(e)}"})

	# Redirect to frontend
	web_origin = settings.WEB_ORIGIN
	resp = RedirectResponse(
			url=f"{web_origin}/auth-callback.html?access_token={access_token}&refresh_token={refresh_token}",
			status_code=302
		)
	
	# Cleanup cookies
	resp.delete_cookie("oauth_state", httponly=True, secure=True, samesite="none")
	resp.delete_cookie("oauth_redirect_uri", httponly=True, secure=True, samesite="none")

	return resp


@router.post("/github/token")
async def cli_exchange_token(
	request: Request,
	db: Session = Depends(get_db),
):
	"""
	CLI-specific endpoint: exchange code + code_verifier for tokens.
	"""
	try:
		body = await request.json()
	except Exception:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid JSON"})
		
	code = body.get("code")
	code_verifier = body.get("code_verifier")
	redirect_uri = body.get("redirect_uri")

	if not code:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing 'code'"})

	try:
		user, access_token, refresh_token = await handle_oauth_callback(
			db=db,
			code=code,
			redirect_uri=redirect_uri,
			code_verifier=code_verifier,
			is_cli=True
		)
	except Exception as e:
		print(f"OAUTH EXCHANGE FAILED: {e}")
		raise HTTPException(status_code=502, detail={"status": "error", "message": f"Token exchange failed: {str(e)}"})

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


@router.post("/refresh")
async def refresh_tokens(request: Request, db: Session = Depends(get_db)):
	refresh_token = None
	try:
		body = await request.json()
		refresh_token = body.get("refresh_token")
	except Exception:
		pass 

	if not refresh_token:
		refresh_token = request.cookies.get("refresh_token")

	if not refresh_token:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing refresh_token"})

	result = rotate_refresh_token(db, refresh_token)
	if not result:
		raise HTTPException(status_code=401, detail={"status": "error", "message": "Invalid or expired refresh token"})

	new_access, new_refresh = result
	return {
		"status": "success",
		"access_token": new_access,
		"refresh_token": new_refresh,
	}


@router.post("/logout")
async def logout(
	request: Request,
	response: Response,
	db: Session = Depends(get_db),
):
	raw_token = None
	try:
		body = await request.json()
		raw_token = body.get("refresh_token")
	except Exception:
		pass

	if not raw_token:
		raw_token = request.cookies.get("refresh_token")

	if not raw_token:
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Missing refresh_token"})

	revoke_refresh_token(db, raw_token)

	# 2. MATCH THE FLAGS EXACTLY TO FORCE BROWSER DELETION
	response.delete_cookie("access_token", httponly=True, secure=True, samesite="none")
	response.delete_cookie("refresh_token", httponly=True, secure=True, samesite="none")

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