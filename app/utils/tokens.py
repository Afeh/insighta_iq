import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
 
from jose import JWTError, jwt
from sqlalchemy.orm import Session
 
from app.config.settings import settings
from app.models.user_models import RefreshToken, User
from uuid_extensions import uuid7str

def _now() -> datetime:
	return datetime.now(timezone.utc)


def create_access_token(user: User) -> str:
	expire = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
	payload = {
		"sub": user.id,
		"username": user.username,
		"role": user.role,
		"exp": expire,
		"iat": _now(),
		"type": "access",
	}
	return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
	"""Raises JWTError if invalid or expired."""
	return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def _hash_token(raw: str) -> str:
	return hashlib.sha256(raw.encode()).hexdigest()

def create_refresh_token(db: Session, user_id: str) -> str:
	raw = secrets.token_urlsafe(48)
	token_hash = _hash_token(raw)
	expires_at = _now() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
 
	rt = RefreshToken(
		id=uuid7str(),
		user_id=user_id,
		token_hash=token_hash,
		expires_at=expires_at,
	)
	db.add(rt)
	db.commit()
	return raw


def rotate_refresh_token(db: Session, raw_token: str) -> tuple[str, str] | None:
	"""
	Validate old refresh token, revoke it, issue new access + refresh token pair.
	Returns (new_access_token, new_refresh_token) or None if invalid.
	"""
	token_hash = _hash_token(raw_token)
	rt = db.query(RefreshToken).filter(
		RefreshToken.token_hash == token_hash,
		RefreshToken.revoked == False,
	).first()
 
	if not rt:
		return None
 
	if rt.expires_at.replace(tzinfo=timezone.utc) < _now():
		rt.revoked = True
		db.commit()
		return None
 
	user = db.query(User).filter(User.id == rt.user_id).first()
	if not user or not user.is_active:
		return None
 
	# Revoke old token immediately
	rt.revoked = True
	db.commit()
 
	new_access = create_access_token(user)
	new_refresh = create_refresh_token(db, user.id)
	return new_access, new_refresh


def revoke_refresh_token(db: Session, raw_token: str) -> bool:
	token_hash = _hash_token(raw_token)
	rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
	if rt:
		rt.revoked = True
		db.commit()
		return True
	return False
 