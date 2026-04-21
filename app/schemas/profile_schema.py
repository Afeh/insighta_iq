from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class ProfileOut(BaseModel):
	id: str
	name: str
	gender: str
	gender_probability: float
	age: int
	age_group: str
	country_id: str
	country_name: str
	country_probability: float
	created_at: datetime

	model_config = {"from_attributes": True}


class PaginatedProfilesResponse(BaseModel):
	status: str = "success"
	page: int
	limit: int
	total: int
	data: List[ProfileOut]


class ErrorResponse(BaseModel):
	status: str = "error"
	message: str