from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserOut(BaseModel):
	id: str
	github_id: str
	username: str
	email: Optional[str]
	avatar_url: Optional[str]
	role: str
	is_active: bool
	last_login_at: Optional[datetime]
	created_at: datetime

	model_config = {"from_attributes": True}

class UserResponse(BaseModel):
	status: str
	data: UserOut


class TokenResponse(BaseModel):
	status: str = "success"
	access_token: str
	refresh_token: str


class RefreshRequest(BaseModel):
	refresh_token: str