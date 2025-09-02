from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from database.base import Base
from core.config import settings

# Import all models so they are registered with SQLAlchemy
from models import *

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,  # Increased pool size for better concurrency
    max_overflow=20,  # Allow more connections when pool is full
    pool_timeout=30,  # 30 second timeout for getting connection from pool
    pool_recycle=3600,  # Recycle connections every hour
    pool_pre_ping=True,  # Verify connections before use
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
    finally:
        db.close() 