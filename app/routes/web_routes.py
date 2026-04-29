from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.middlewares.auth_middleware import get_current_user
from app.models.user_models import User
from typing import Optional

router = APIRouter(tags=["web-portal"])
templates = Jinja2Templates(directory="templates")

# Public Route
@router.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    # If user already has a valid token, redirect to dashboard
    return templates.TemplateResponse(request=request, name="login.html")

# Protected Routes
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"user": user})

@router.get("/web/profiles", response_class=HTMLResponse)
async def profiles_list_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="profiles.html", context={"user": user})

@router.get("/web/profiles/{profile_id}", response_class=HTMLResponse)
async def profile_detail_page(request: Request, profile_id: str, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="profile_detail.html", context={"user": user, "profile_id": profile_id})

@router.get("/web/account", response_class=HTMLResponse)
async def account_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="account.html", context={"user": user})