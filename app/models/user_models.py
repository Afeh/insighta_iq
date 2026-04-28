from sqlalchemy import Column, String, Boolean, DateTime, func, Text
from app.db.database import Base
 
 
class User(Base):
	__tablename__ = "users"
 
	id = Column(String(36), primary_key=True)
	github_id = Column(String, nullable=False, unique=True)
	username = Column(String, nullable=False)
	email = Column(String, nullable=True)
	avatar_url = Column(String, nullable=True)
	role = Column(String, nullable=False, default="analyst")
	is_active = Column(Boolean, nullable=False, default=True)
	last_login_at = Column(DateTime(timezone=True), nullable=True)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
 
 
class RefreshToken(Base):
	__tablename__ = "refresh_tokens"
 
	id = Column(String(36), primary_key=True)
	user_id = Column(String(36), nullable=False)
	token_hash = Column(String, nullable=False, unique=True)
	expires_at = Column(DateTime(timezone=True), nullable=False)
	revoked = Column(Boolean, nullable=False, default=False)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)