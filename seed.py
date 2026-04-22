import json
from uuid_extensions import uuid7str
from sqlalchemy.orm import Session
from app.db.database import SessionLocal, engine
from app.models.profile_models import Profile

def seed_database():
	with open('seed_profiles.json', 'r') as f:
		data = json.load(f)
	
	profiles_data = data.get("profiles", [])
	
	# 2. Create a database session
	db = SessionLocal()
	
	try:
		print(f"Seeding {len(profiles_data)} profiles...")
		
		for p in profiles_data:
			# Check if profile already exists by name to avoid UniqueConstraint errors
			exists = db.query(Profile).filter(Profile.name == p['name']).first()
			if exists:
				continue

			new_profile = Profile(
				id=uuid7str(),
				name=p['name'],
				gender=p['gender'],
				gender_probability=p['gender_probability'],
				age=p['age'],
				age_group=p['age_group'],
				country_id=p['country_id'],
				country_name=p['country_name'],
				country_probability=p['country_probability']
				# created_at is handled by server_default=func.now()
			)
			db.add(new_profile)
		
		db.commit()
		print("Database seeded successfully!")
		
	except Exception as e:
		print(f"Error seeding database: {e}")
		db.rollback()
	finally:
		db.close()

if __name__ == "__main__":
	seed_database()