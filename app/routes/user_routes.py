from app.models.user_models import User
from app.middlewares.auth_middleware import get_current_user
from fastapi import APIRouter, Depends


router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me")
def get_my_profile(current_user: User = Depends(get_current_user)):
	return {
		"status": "success",
		"data": {
			"id": current_user.id,
			"username": current_user.username,
			"email": current_user.email,
			"avatar_url": current_user.avatar_url,
			"role": current_user.role,
			"is_active": current_user.is_active,
			"last_login_at": current_user.last_login_at,
		}
	}