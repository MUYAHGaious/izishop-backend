from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from database.base import Base
from core.config import settings

# Import all models so they are registered with SQLAlchemy
from models import *

# Create database engine with optimized connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=5,  # Reduced pool size to prevent connection exhaustion
    max_overflow=10,  # Allow more connections when pool is full
    pool_timeout=20,  # 20 second timeout for getting connection from pool
    pool_recycle=1800,  # Recycle connections every 30 minutes
    pool_pre_ping=True,  # Verify connections before use
    echo=False,  # Disable SQL logging for performance
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create all tables
def create_tables():
    Base.metadata.create_all(bind=engine)

# Dependency to get database session
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close() 