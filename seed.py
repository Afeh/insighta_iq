# seed_users.py
from app.db.database import SessionLocal
from app.models.user_models import User
from app.utils.tokens import create_access_token, create_refresh_token
from uuid_extensions import uuid7str
from datetime import datetime, timezone

def main():
    db = SessionLocal()

    def seed_and_get_tokens(username, email, role, github_id):
        # Look for existing user by role
        user = db.query(User).filter(User.role == role).first()
        
        if not user:
            user = User(
                id=uuid7str(),
                github_id=github_id,
                username=username,
                email=email,
                role=role,
                is_active=True,
                last_login_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created new {role} user!")
        else:
            print(f"Found existing {role} user.")

        # Generate fresh tokens
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(db, user.id)
        
        print(f"\n--- {role.upper()} TOKENS ---")
        print(f"Access Token ({role}):\n{access_token}")
        if role == "admin":
            print(f"\nRefresh Token (admin):\n{refresh_token}")
        print("-" * 30)

    print("Seeding Admin...")
    seed_and_get_tokens("admin_user", "admin@insighta.com", "admin", "admin_github_001")
    
    print("\nSeeding Analyst...")
    seed_and_get_tokens("analyst_user", "analyst@insighta.com", "analyst", "analyst_github_002")

if __name__ == "__main__":
    main()