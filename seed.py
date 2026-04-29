from app.db.database import SessionLocal
from app.models.user_models import User
from uuid_extensions import uuid7str

db = SessionLocal()

# Seed Admin
if not db.query(User).filter(User.role == "admin").first():
    admin = User(
        id=uuid7str(),
        username="admin_tester",
        email="admin@example.com",
        role="admin",
        is_active=True,
        github_id=uuid7str()
    )
    db.add(admin)

# Seed Analyst
if not db.query(User).filter(User.role == "analyst").first():
    analyst = User(
        id=uuid7str(),
        username="analyst_tester",
        email="analyst@example.com",
        role="analyst",
        is_active=True,
        github_id=uuid7str()
    )
    db.add(analyst)

db.commit()
print("Database seeded with Admin and Analyst!")