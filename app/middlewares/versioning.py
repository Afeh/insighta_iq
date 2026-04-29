from fastapi import Request, HTTPException

def require_api_version(request: Request):
	version = request.headers.get("X-API-Version")

	if version != "1":
		raise HTTPException(
			status_code=400,
			detail={
				"status": "error",
				"message": "API version header required"
			}
		)