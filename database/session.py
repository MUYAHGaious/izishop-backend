from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from decouple import config

DATABASE_URL = config("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=True, future=True)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

def get_db():
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        db.close() 