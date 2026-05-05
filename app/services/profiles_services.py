import httpx
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc, func
from typing import Optional, Tuple, List
from uuid_extensions import uuid7str

from app.models.profile_models import Profile
from app.config.settings import settings
from app.utils.round_up import round_up
from app.services.nlp_parser import parse_natural_query, ParsedQuery, COUNTRY_MAP
from app.services.cache_service import get_cache, QUERY_CACHE_PREFIX
from app.services.query_normalizer import (
	normalize_filter_params,
	normalize_parsed_query
)

REVERSE_COUNTRY_MAP = {code: name.title() for name, code in COUNTRY_MAP.items()}

VALID_SORT_FIELDS = {"age", "created_at", "gender_probability"}
VALID_ORDERS = {"asc", "desc"}
VALID_AGE_GROUPS = {"child", "teenager", "adult", "senior"}
VALID_GENDERS = {"male", "female"}

QUERY_CACHE_TTL = 300  # 5 minutes


class QueryValidationError(Exception):
	def __init__(self, message: str, status_code: int = 400):
		self.message = message
		self.status_code = status_code
		super().__init__(message)


def _profile_to_dict(profile: Profile) -> dict:
	"""Convert SQLAlchemy Profile model to dict"""
	return {
		"id": profile.id,
		"name": profile.name,
		"gender": profile.gender,
		"gender_probability": profile.gender_probability,
		"age": profile.age,
		"age_group": profile.age_group,
		"country_id": profile.country_id,
		"country_name": profile.country_name,
		"country_probability": profile.country_probability,
		"created_at": profile.created_at.isoformat() if profile.created_at else None,
	}


def _apply_filter(
	query,
	gender: Optional[str] = None,
	age_group: Optional[str] = None,
	country_id: Optional[str] = None,
	min_age: Optional[int] = None,
	max_age: Optional[int] = None,
	min_gender_probability: Optional[float] = None,
	min_country_probability: Optional[float] = None
):
	if gender is not None:
		if gender not in VALID_GENDERS:
			raise QueryValidationError("Invalid value for 'gender'. Must be 'male' or 'female'.", 422)
		query = query.filter(Profile.gender == gender)

	if age_group is not None:
		if age_group not in VALID_AGE_GROUPS:
			raise QueryValidationError("Invalid value for 'age_group'. Must be one of: child, teenager, adult, senior", 422)
		query = query.filter(Profile.age_group == age_group)

	if country_id is not None:
		query = query.filter(func.upper(Profile.country_id) == country_id.upper())

	if min_age is not None:
		query = query.filter(Profile.age >= min_age)

	if max_age is not None:
		query = query.filter(Profile.age <= max_age)

	if min_gender_probability is not None:
		query = query.filter(Profile.gender_probability >= min_gender_probability)
	
	if min_country_probability is not None:
		query = query.filter(Profile.country_probability >= min_country_probability)
	
	return query


def _apply_sorting(query, sort_by: Optional[str], order: Optional[str]):
	if sort_by is not None:
		if sort_by not in VALID_SORT_FIELDS:
			raise QueryValidationError(
				f"Invalid 'sort_by' value. Must be one of: {', '.join(VALID_SORT_FIELDS)}.", 422
			)
	if order is not None and order not in VALID_ORDERS:
		raise QueryValidationError("Invalid 'order' value. Must be 'asc' or 'desc'.", 422)
	
	if sort_by:
		col = getattr(Profile, sort_by)
		query = query.order_by(asc(col) if order != "desc" else desc(col))
	else:
		query = query.order_by(asc(Profile.created_at))
	
	return query


def _apply_pagination(query, page: int, limit: int) -> Tuple[int, list]:
	if page < 1:
		raise QueryValidationError("'page' must be a positive integer.", 422)
	if limit < 1 or limit > 50:
		raise QueryValidationError("'limit' must be between 1 and 50", 422)
	
	total = query.count()
	results = query.offset((page - 1) * limit).limit(limit).all()
	return total, results


def get_profiles(
	db: Session,
	gender: Optional[str] = None,
	age_group: Optional[str] = None,
	country_id: Optional[str] = None,
	min_age: Optional[int] = None,
	max_age: Optional[int] = None,
	min_gender_probability: Optional[float] = None,
	min_country_probability: Optional[float] = None,
	sort_by: Optional[str] = None,
	order: Optional[str] = "asc",
	page: int = 1,
	limit: int = 10,
):
	# Normalize parameters to canonical form
	normalized = normalize_filter_params(
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
		limit=limit
	)
	
	# Generate cache key from normalized parameters
	cache_key = normalized.to_cache_key("")
	
	# Check cache first
	cache = get_cache()
	cached_result = cache.get(cache_key)
	if cached_result is not None:
		return cached_result
	
	# Query database
	query = db.query(Profile)
	query = _apply_filter(
		query, 
		gender=normalized.gender,
		age_group=normalized.age_group,
		country_id=normalized.country_id,
		min_age=normalized.min_age,
		max_age=normalized.max_age,
		min_gender_probability=normalized.min_gender_probability,
		min_country_probability=normalized.min_country_probability
	)
	query = _apply_sorting(query, normalized.sort_by, normalized.order)
	total, results = _apply_pagination(query, normalized.page, normalized.limit)
	
	# Cache the result (convert to dict format for JSON serialization)
	cached_result = (total, [_profile_to_dict(r) for r in results])
	cache.set(cache_key, cached_result, ttl=QUERY_CACHE_TTL)
	
	return total, results


def search_profiles_nlp(
	db: Session,
	q: str,
	page: int = 1,
	limit: int = 10
):
	# Normalize the NLP parsed query
	parsed = parse_natural_query(q)

	if not parsed.valid:
		return None
	
	# Normalize to canonical form for caching
	normalized = normalize_parsed_query(parsed)
	normalized.page = page
	normalized.limit = limit
	
	# Generate cache key
	cache_key = normalized.to_cache_key()
	
	# Check cache
	cache = get_cache()
	cached_result = cache.get(cache_key)
	if cached_result is not None:
		return cached_result
	
	# Query database
	query = db.query(Profile)

	gender_filter = None if normalized.both_genders else normalized.gender
	query = _apply_filter(
		query,
		gender=gender_filter,
		age_group=normalized.age_group,
		country_id=normalized.country_id,
		min_age=normalized.min_age,
		max_age=normalized.max_age
	)
	query = query.order_by(asc(Profile.created_at))
	total, results = _apply_pagination(query, normalized.page, normalized.limit)
	
	# Cache the result (convert to dict format for JSON serialization)
	cached_result = (total, [_profile_to_dict(r) for r in results])
	cache.set(cache_key, cached_result, ttl=QUERY_CACHE_TTL)
	
	return total, results


async def fetch_gender(name: str):
	async with httpx.AsyncClient() as client:
		res = await client.get(
			settings.GENDERIZE_API_URL,
			params={"name": name}
		)

	if res.status_code != 200:
		raise ValueError("Genderize")

	data = res.json()

	if data.get("gender") is None or data.get("count") == 0:
		raise ValueError("Genderize")
	
	return {
		"gender": data["gender"],
		"probability": data["probability"],
		"count": data["count"]
	}


async def fetch_age(name: str):
	async with httpx.AsyncClient() as client:
		res = await client.get(
			settings.AGIFY_API_URL,
			params={"name": name}
		)

	if res.status_code != 200:
		raise ValueError("Agify")

	data = res.json()

	if data.get("age") is None:
		raise ValueError("Agify")

	return {
		"age": data["age"]
	}


async def fetch_country(name: str):
	async with httpx.AsyncClient() as client:
		res = await client.get(
			settings.NATIONALIZE_API_URL,
			params={"name": name}
		)
	if res.status_code != 200:
		raise ValueError("Nationalize")

	data = res.json()

	countries = data.get("country", [])
	if not countries:
		raise ValueError("Nationalize")

	return countries


async def create_profile_from_external_apis(db: Session, name: str) -> Profile:
	existing_profile = db.query(Profile).filter(func.lower(Profile.name) == name.lower()).first()

	if existing_profile:
		return existing_profile, False

	try:
		gender_data, age_data, country_data = await asyncio.gather(
			fetch_gender(name),
			fetch_age(name),
			fetch_country(name)
		)
	except ValueError as e:
		raise ValueError(str(e))

	# 3. Process age group
	age = age_data["age"]

	if age <= 12:
		age_group = "child"
	elif age <= 19:
		age_group = "teenager"
	elif age <= 59:
		age_group = "adult"
	else:
		age_group = "senior"

	# 4. Pick best country (highest probability)
	best_country = max(country_data, key=lambda x: x["probability"])

	new_profile = Profile(
		id=uuid7str(),
		name=name,
		gender=gender_data["gender"],
		gender_probability=gender_data["probability"],
		age=age,
		age_group=age_group,
		country_id=best_country["country_id"],
		country_name=REVERSE_COUNTRY_MAP[best_country["country_id"]],
		country_probability=round_up(best_country["probability"]),
		created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
	)

	db.add(new_profile)
	db.commit()
	db.refresh(new_profile)

	return new_profile, True


def get_profile_by_id(db: Session, id: str):
	return db.query(Profile).filter(Profile.id == id).first()