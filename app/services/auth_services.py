import hashlib
import base64
import secrets
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from urllib.parse import urlencode

from app.config.settings import settings
from app.models.user_models import User
from uuid_extensions import uuid7str
from app.utils.tokens import create_access_token, create_refresh_token



GITHUB_AUTHORIZE_URL = settings.GITHUB_AUTHORIZE_URL
GITHUB_TOKEN_URL = settings.GITHUB_TOKEN_URL
GITHUB_USER_URL = settings.GITHUB_USER_URL


# ---------------------------------------------------------------------------
# PKCE helpers (used by CLI)
# ---------------------------------------------------------------------------

def generate_pkce_pair() -> tuple[str, str]:
	"""Returns (code_verifier, code_challenge)."""
	code_verifier = secrets.token_urlsafe(64)
	digest = hashlib.sha256(code_verifier.encode()).digest()
	code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
	return code_verifier, code_challenge


def verify_code_challenge(code_verifier: str, code_challenge: str) -> bool:
	digest = hashlib.sha256(code_verifier.encode()).digest()
	expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
	return expected == code_challenge


# ---------------------------------------------------------------------------
# OAuth URL builder
# ---------------------------------------------------------------------------

def build_github_auth_url(
	state: str,
	code_challenge: Optional[str] = None,
	redirect_uri: Optional[str] = None,
	is_cli: bool = False

) -> str:

	client_id = (
		settings.GITHUB_CLIENT_ID_CLI
		if is_cli
		else settings.GITHUB_CLIENT_ID
	)

	params = {
		"client_id": client_id,
		"redirect_uri": redirect_uri or settings.GITHUB_REDIRECT_URI,
		"scope": "read:user user:email",
		"state": state,
	}
	if code_challenge:
		params["code_challenge"] = code_challenge
		params["code_challenge_method"] = "S256"

	return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Token exchange + user info
# ---------------------------------------------------------------------------

async def exchange_code_for_token(
	code: str,
	redirect_uri: Optional[str] = None,
	code_verifier: Optional[str] = None,
) -> str:
	"""Exchange OAuth code for GitHub access token."""

	is_cli = code_verifier is not None

	client_id = (
		settings.GITHUB_CLIENT_ID_CLI
		if is_cli
		else settings.GITHUB_CLIENT_ID
	)

	client_secret = (
		settings.GITHUB_CLIENT_SECRET_CLI
		if is_cli
		else settings.GITHUB_CLIENT_SECRET
	)

	payload = {
		"client_id": client_id,
		"client_secret": client_secret,
		"code": code,
		"redirect_uri": redirect_uri or settings.GITHUB_REDIRECT_URI,
	}
	if code_verifier:
		payload["code_verifier"] = code_verifier

	async with httpx.AsyncClient() as client:
		resp = await client.post(
			GITHUB_TOKEN_URL,
			data=payload,
			headers={"Accept": "application/json"},
		)
		resp.raise_for_status()
		data = resp.json()

	if "error" in data:
		raise ValueError(f"GitHub OAuth error: {data.get('error_description', data['error'])}")

	return data["access_token"]


async def fetch_github_user(github_token: str) -> dict:
	async with httpx.AsyncClient() as client:
		resp = await client.get(
			GITHUB_USER_URL,
			headers={
				"Authorization": f"Bearer {github_token}",
				"Accept": "application/vnd.github+json",
			},
		)
		resp.raise_for_status()
		return resp.json()


# ---------------------------------------------------------------------------
# User upsert
# ---------------------------------------------------------------------------

def upsert_user(db: Session, github_user: dict) -> User:
	"""Create or update a user from GitHub profile data."""
	github_id = str(github_user["id"])
	user = db.query(User).filter(User.github_id == github_id).first()

	now = datetime.now(timezone.utc)

	if user:
		user.username = github_user.get("login", user.username)
		user.email = github_user.get("email") or user.email
		user.avatar_url = github_user.get("avatar_url") or user.avatar_url
		user.last_login_at = now
	else:
		user = User(
			id=uuid7str(),
			github_id=github_id,
			username=github_user.get("login", ""),
			email=github_user.get("email"),
			avatar_url=github_user.get("avatar_url"),
			role="analyst",   # default role
			is_active=True,
			last_login_at=now,
		)
		db.add(user)

	db.commit()
	db.refresh(user)
	return user


# ---------------------------------------------------------------------------
# Full callback handler (shared by browser + CLI)
# ---------------------------------------------------------------------------

async def handle_oauth_callback(
	db: Session,
	code: str,
	redirect_uri: Optional[str] = None,
	code_verifier: Optional[str] = None,
) -> tuple[User, str, str]:
	"""
	Exchange code → GitHub token → user info → upsert user → issue tokens.
	Returns (user, access_token, refresh_token).
	"""
	github_token = await exchange_code_for_token(code, redirect_uri, code_verifier)
	github_user = await fetch_github_user(github_token)
	user = upsert_user(db, github_user)

	access_token = create_access_token(user)
	refresh_token = create_refresh_token(db, user.id)

	return user, access_token, refresh_token