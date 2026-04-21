from sqlalchemy import Column, String, Float, Integer, DateTime, func
from app.db.database import Base


class Profile(Base):
	__tablename__ = "profiles"

	id  = Column(String(36), primary_key=True)
	name = Column(String, nullable=False, unique=True)
	gender = Column(String, nullable=False)
	gender_probability = Column(Float, nullable=False)
	age = Column(Integer, nullable=False)
	age_group = Column(String, nullable=False)
	country_id = Column(String(2), nullable=False)
	country_name = Column(String, nullable=False)
	country_probability = Column(Float, nullable=False)
	created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)