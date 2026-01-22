from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
DATABASE_URL = "postgresql+psycopg2://postgres:12345@127.0.0.1:5432/home_surveillance_db"

# Create engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()