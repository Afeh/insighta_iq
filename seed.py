# Run this once in a shell/seed script
# seed_analyst.py
from app.db.database import SessionLocal
from app.models.user_models import User
from app.utils.tokens import create_access_token, create_refresh_token
from uuid_extensions import uuid7str
from datetime import datetime, timezone

db = SessionLocal()

analyst = db.query(User).filter(User.role == "analyst").first()
if not analyst:
    analyst = User(
        id=uuid7str(),
        github_id="test_analyst_001",
        username="test_analyst",
        email="analyst@test.com",
        role="analyst",
        is_active=True,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(analyst)
    db.commit()
    db.refresh(analyst)

token = create_access_token(analyst)
refresh = create_refresh_token(db, analyst.id)
print("Analyst token:", token)
print("Refresh token:", refresh)