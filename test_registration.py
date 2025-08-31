"""
Minimal test to debug registration hanging issue
"""
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
import uvicorn
from sqlalchemy.orm import Session
from database.connection import get_db
from models.user import User, UserRole
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

class SimpleRegister(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    role: str = "CUSTOMER"

@app.get("/")
async def root():
    return {"message": "Test registration API"}

@app.post("/test-register")
async def test_register(user_data: SimpleRegister):
    """Simple registration test without complex validation"""
    try:
        logger.info(f"Received registration request for: {user_data.email}")
        
        # Just return success without database operations first
        return {
            "message": "Registration test successful",
            "email": user_data.email,
            "role": user_data.role
        }
        
    except Exception as e:
        logger.error(f"Error in test registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/test-db-register")
async def test_db_register(user_data: SimpleRegister):
    """Test with database operations"""
    try:
        logger.info(f"Testing DB registration for: {user_data.email}")
        
        # Test database connection
        db = next(get_db())
        logger.info("Database connection successful")
        
        # Test simple query
        user_count = db.query(User).count()
        logger.info(f"Current user count: {user_count}")
        
        # Test user check
        existing_user = db.query(User).filter(User.email == user_data.email).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already exists"
            )
        
        logger.info("Database operations successful")
        
        return {
            "message": "Database test successful",
            "email": user_data.email,
            "user_count": user_count
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in DB test: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
