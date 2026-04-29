import csv
from datetime import datetime
import io
import math
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.db.database import get_db
from app.schemas.profile_schema import PaginatedProfilesResponse, ProfileOut, ErrorResponse, CreateProfileRequest
from app.services.profiles_services import get_profiles, search_profiles_nlp, create_profile_from_external_apis, get_profile_by_id , QueryValidationError
from app.middlewares.auth_middleware import require_admin, require_analyst_or_admin
from app.middlewares.versioning import require_api_version

router = APIRouter(prefix="/api/profiles", tags=["profiles"], dependencies=[Depends(require_api_version)])


def _paginated_response(request: Request, total: int, page: int, limit: int, results) -> dict:
	total_pages = math.ceil(total / limit) if limit > 0 else 0
	
	def get_page_url(p: int):
		if p < 1 or p > total_pages:
			return None
		return str(request.url.include_query_params(page=p, limit=limit))

	return {
		"status": "success",
		"page": page,
		"limit": limit,
		"total": total,
		"total_pages": total_pages,
		"links": {
			"self": str(request.url.include_query_params(page=page, limit=limit)),
			"next": get_page_url(page + 1) if page < total_pages else None,
			"prev": get_page_url(page - 1) if page > 1 else None
		},
		"data": results,
	}

@router.get("/search")
def search_profiles(
	request: Request,
	q: str = Query(..., description="Natural language query string"),
	page: int = Query(1, ge=1),
	limit: int = Query(10, ge=1, le=50),
	db: Session = Depends(get_db),
	user=Depends(require_analyst_or_admin)
):
	"""
	Natural language profile search.
	Example: /api/profiles/search?q=young males from nigeria
	"""
	if not q or not q.strip():
		raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid query parameters"})

	try:
		result = search_profiles_nlp(db, q.strip(), page=page, limit=limit)
	except QueryValidationError as e:
		raise HTTPException(
			status_code=e.status_code,
			detail={"status": "error", "message": e.message},
		)

	if result is None:
		raise HTTPException(
			status_code=400,
			detail={"status": "error", "message": "Unable to interpret query"},
		)

	total, profiles = result
	return _paginated_response(request=request, total=total, page=page, limit=limit, results=profiles)


@router.get("")
def list_profiles(
	request: Request,
	gender: Optional[str] = Query(None),
	age_group: Optional[str] = Query(None),
	country_id: Optional[str] = Query(None),
	min_age: Optional[int] = Query(None, ge=0),
	max_age: Optional[int] = Query(None, ge=0),
	min_gender_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
	min_country_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
	sort_by: Optional[str] = Query(None),
	order: Optional[str] = Query("asc"),
	page: int = Query(1, ge=1),
	limit: int = Query(10, ge=1, le=50),
	db: Session = Depends(get_db),
	user=Depends(require_analyst_or_admin)
):
	"""
	List profiles with advanced filtering, sorting, and pagination.
	All filters are combinable.
	"""
	try:
		total, profiles = get_profiles(
			db,
			gender=gender,
			age_group=age_group,
			country_id=country_id,
			min_age=min_age,
			max_age=max_age,
			min_gender_probability=min_gender_probability,
			min_country_probability=min_country_probability,
			sort_by=sort_by,
			order=order,
			page=page,
			limit=limit,
		)
	except QueryValidationError as e:
		raise HTTPException(
			status_code=e.status_code,
			detail={"status": "error", "message": e.message},
		)

	return _paginated_response(request=request, total=total, page=page, limit=limit, results=profiles)


@router.get("/export")
def export_profiles(
	# Use the same filters as list_profiles
	gender: Optional[str] = Query(None),
	age_group: Optional[str] = Query(None),
	country_id: Optional[str] = Query(None),
	min_age: Optional[int] = Query(None, ge=0),
	max_age: Optional[int] = Query(None, ge=0),
	min_gender_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
	min_country_probability: Optional[float] = Query(None, ge=0.0, le=1.0),
	sort_by: Optional[str] = Query(None),
	order: Optional[str] = Query("asc"),
	format: str = Query(..., description="Must be csv"),
	page: int = Query(1, ge=1),
	limit: int = Query(10, ge=1, le=50),
	db: Session = Depends(get_db),
	user=Depends(require_analyst_or_admin)
):
	if format.lower() != "csv":
		raise HTTPException(
			status_code=400, 
			detail={"status": "error", "message": "Only CSV format is supported"}
		)

	try:
		_, profiles = get_profiles(
			db, gender, age_group, country_id, min_age, max_age, 
			min_gender_probability, min_country_probability, 
			sort_by, order, page=page, limit=limit 
		)
	except QueryValidationError as e:
		raise HTTPException(status_code=e.status_code, detail={"status": "error", "message": e.message})

	# Create CSV in memory
	output = io.StringIO()
	writer = csv.writer(output)
	
	writer.writerow([
		"id", "name", "gender", "gender_probability", "age", 
		"age_group", "country_id", "country_name", "country_probability", "created_at"
	])
	
	# Write Rows
	for p in profiles:
		writer.writerow([
			p.id, p.name, p.gender, p.gender_probability, p.age, 
			p.age_group, p.country_id, p.country_name, p.country_probability, p.created_at
		])

	output.seek(0)
	timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
	
	return StreamingResponse(
		iter([output.getvalue()]),
		media_type="text/csv",
		headers={"Content-Disposition": f'attachment; filename="profiles_{timestamp}.csv"'}
	)

@router.post("")
async def create_profile(
	payload: CreateProfileRequest,
	db: Session = Depends(get_db),
	user=Depends(require_admin)
):
	"""
	Admin Only: Calls external APIs to generate a profile from a name.
	"""
	try:
		
		profile, is_new = await create_profile_from_external_apis(db, payload.name) # <-- Added await
	except Exception as e:
		print(e)
		raise HTTPException(status_code=500, detail={"status": "error", "message": str(e)})

	# Format the data cleanly
	profile_data = {
		"id": str(profile.id),
		"name": profile.name,
		"gender": profile.gender,
		"gender_probability": profile.gender_probability,
		"age": profile.age,
		"age_group": profile.age_group,
		"country_id": profile.country_id,
		"country_name": profile.country_name,
		"country_probability": profile.country_probability,
		"created_at": profile.created_at.isoformat() if profile.created_at else None
	}

	# If it already existed, return your custom message
	if not is_new:
		return {
			"status": "success",
			"message": "Profile already exists",
			"data": profile_data
		}

	# If it was just created, return standard success
	return {
		"status": "success",
		"data": profile_data
	}


@router.get("/{id}")
async def get_profile_id(
	id: str,
	db: Session = Depends(get_db),
	user=Depends(require_analyst_or_admin)
):
	profile = get_profile_by_id(db=db, id=id)

	if not profile:
		raise HTTPException(
			status_code=404, 
			detail={"status": "error", "message": "Profile not found"}
		)

	# 2. Return the formatted data
	return {
		"status": "success",
		"data": {
			"id": str(profile.id),
			"name": profile.name,
			"gender": profile.gender,
			"gender_probability": profile.gender_probability,
			"age": profile.age,
			"age_group": profile.age_group,
			"country_id": profile.country_id,
			"country_name": profile.country_name,
			"country_probability": profile.country_probability,
			"created_at": profile.created_at.isoformat() if profile.created_at else None
		}
	}