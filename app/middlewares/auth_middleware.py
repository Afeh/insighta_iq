from fastapi import Depends, HTTPException, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session
from typing import Optional
 
from app.db.database import get_db
from app.models.user_models import User
from app.utils.tokens import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

def _extract_token(
	request: Request,
	credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
	"""Try Bearer header first, then fall back to HTTP-only cookie."""
	if credentials and credentials.credentials:
		return credentials.credentials
	return request.cookies.get("access_token")


def get_current_user(
	request: Request,
	credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
	db: Session = Depends(get_db),
) -> User:
	token = _extract_token(request, credentials)
	if not token:
		raise HTTPException(
			status_code=401,
			detail={"status": "error", "message": "Authentication required"},
		)
	try:
		payload = decode_access_token(token)
	except JWTError:
		raise HTTPException(
			status_code=401,
			detail={"status": "error", "message": "Invalid or expired token"},
		)
 
	user = db.query(User).filter(User.id == payload.get("sub")).first()
	if not user:
		raise HTTPException(
			status_code=401,
			detail={"status": "error", "message": "User not found"},
		)
	if not user.is_active:
		raise HTTPException(
			status_code=403,
			detail={"status": "error", "message": "Account is deactivated"},
		)
	return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
	if current_user.role != "admin":
		raise HTTPException(
			status_code=403,
			detail={"status": "error", "message": "Admin access required"},
		)
	return current_user


def require_analyst_or_admin(current_user: User = Depends(get_current_user)) -> User:
	"""analyst and admin both have read access."""
	if current_user.role not in ("admin", "analyst"):
		raise HTTPException(
			status_code=403,
			detail={"status": "error", "message": "Access denied"},
		)
	return current_user