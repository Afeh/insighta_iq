import time
from fastapi import Request
from fastapi.responses import JSONResponse
import jwt # Add this to decode the token
from app.config.settings import settings 

# In-memory store
request_store = {}

AUTH_LIMIT = 10
DEFAULT_LIMIT = 60
WINDOW = 60  # seconds

def get_client_key(request: Request):
	"""
	Identify the user:
	- Auth routes → use IP
	- Other routes → use user ID from JWT token (if authenticated)
	"""
	if request.url.path.startswith("/auth"):
		return request.client.host

	auth_header = request.headers.get("Authorization")
	if auth_header and auth_header.startswith("Bearer "):
		token = auth_header.split(" ")[1]
		try:

			payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
			user_id = payload.get("sub")
			if user_id:
				return user_id
		except Exception:
			pass 

	
	return request.client.host


async def rate_limit_middleware(request: Request, call_next):
	path = request.url.path

	if path.startswith("/auth"):
		limit = AUTH_LIMIT
	else:
		limit = DEFAULT_LIMIT

	key = get_client_key(request)
	now = time.time()

	if key not in request_store:
		request_store[key] = []

	# Remove expired timestamps
	request_store[key] = [t for t in request_store[key] if now - t < WINDOW]

	if len(request_store[key]) >= limit:
		return JSONResponse(
			status_code=429,
			content={"status": "error", "message": "Too many requests. Please try again later."}
		)

	request_store[key].append(now)

	response = await call_next(request)

	# Inject Rate Limit Headers
	response.headers["X-RateLimit-Limit"] = str(limit)
	response.headers["X-RateLimit-Remaining"] = str(limit - len(request_store[key]))

	return response