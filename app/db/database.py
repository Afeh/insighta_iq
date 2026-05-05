from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import QueuePool
from app.config.settings import settings


# Optimized connection pool configuration for high-concurrency workloads
engine = create_engine(
	settings.DATABASE_URL,
	poolclass=QueuePool,
	pool_size=20,              # Base pool size increased for concurrent queries
	max_overflow=40,           # Allow up to 40 overflow connections
	pool_pre_ping=True,        # Test connections before using them
	pool_recycle=3600,         # Recycle connections every hour (avoid stale connections)
	echo=False,                # Set to True for SQL debugging
	connect_args={
		"connect_timeout": 10,
		"options": "-c statement_timeout=30000"  # 30 second statement timeout
	}
)

# Add connection event listeners for better handling
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
	"""Set useful pragmas for the database connection."""
	try:
		cursor = dbapi_connection.cursor()
		# For PostgreSQL, set work_mem for query optimization
		cursor.execute("SET work_mem = '256MB'")
		cursor.close()
	except Exception:
		pass  # Some databases don't support this


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
	pass


def get_db():

	db = SessionLocal()

	try:
		yield db
	finally:
		db.close()
