from fastapi import Depends
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError

from app.config.settings import settings
from app.routes.profile_routes import router as profiles_router
from app.models.user_models import User
from app.middlewares.auth_middleware import get_current_user
from app.routes.user_routes import router as user_router
from app.routes.auth_routes import router as auth_router
from app.routes.web_routes import router as web_router
from app.middlewares.rate_limit import rate_limit_middleware
from app.middlewares.logging import logging_middleware

from starlette.exceptions import HTTPException as StarletteHTTPException

app = FastAPI(
	title="Insighta IQ"
)

app.add_middleware(
	CORSMiddleware,
	allow_origins=['*'],
	allow_methods=["*"],
	allow_headers=["*"],
	allow_credentials=True,
	allow_origin_regex=".*",
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.middleware("http")(rate_limit_middleware)

app.middleware("http")(logging_middleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
	return JSONResponse(
		status_code=422,
		content={"status": "error", "message": "Invalid query parameters"},
	)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
	return JSONResponse(
		status_code=404,
		content={"status": "error", "message": "Resource not found"},
	)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
	return JSONResponse(
		status_code=500,
		content={"status": "error", "message": "Internal server error"},
	)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
	if isinstance(exc.detail, dict):
		return JSONResponse(status_code=exc.status_code, content=exc.detail)
	
	return JSONResponse(
		status_code=exc.status_code,
		content={"status": "error", "message": str(exc.detail)},
	)

@app.exception_handler(Exception)
async def http_exception_handler(request: Request, exc):
	from fastapi import HTTPException
	if isinstance(exc, HTTPException):
		if isinstance(exc.detail, dict):
			return JSONResponse(status_code=exc.status_code, content=exc.detail)
		return JSONResponse(
			status_code=exc.status_code,
			content={"status": "error", "message": str(exc.detail)},
		)
	return JSONResponse(
		status_code=500,
		content={"status": "error", "message": "Internal server error"},
	)


app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(user_router)


@app.get("/", tags=["health"])
def root():
	return {"status": "success", "message": "Stero API – Intelligence Query Engine v2.0"}


@app.get("/health", tags=["health"])
def health():
	return {"status": "success", "message": "OK"}

