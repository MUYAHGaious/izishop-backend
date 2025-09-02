#!/usr/bin/env python3
"""Debug script to test full registration flow."""

import sys
sys.path.append('.')

from sqlalchemy.orm import Session
from database.connection import get_db, create_tables
from services.auth import create_user, create_access_token, create_refresh_token
from models.user import UserRole
from schemas.user import UserResponse, Token
from datetime import timedelta
from core.config import settings
import traceback
import uuid

def test_full_registration():
    """Test full registration flow including token creation."""
    print("Starting full registration test...")
    
    try:
        # Create tables first
        print("Creating database tables...")
        create_tables()
        print("Tables created successfully")
        
        # Get database session
        db = next(get_db())
        
        # Generate unique email
        unique_id = str(uuid.uuid4())[:8]
        email = f"fulltest_{unique_id}@example.com"
        
        print(f"Creating test user with email: {email}")
        user = create_user(
            db=db,
            email=email,
            password="testpassword123",
            first_name="Full",
            last_name="Test",
            role=UserRole.CUSTOMER,
            phone="1111111111"
        )
        
        print(f"User created successfully: {user.email} with ID: {user.id}")
        
        # Test UserResponse creation
        print("Creating UserResponse...")
        user_response = UserResponse.from_orm(user)
        print(f"UserResponse created: {user_response.email}")
        
        # Test token creation
        print("Creating access token...")
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id)},
            expires_delta=access_token_expires
        )
        print("Access token created successfully")
        
        print("Creating refresh token...")
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )
        print("Refresh token created successfully")
        
        # Test Token response
        print("Creating Token response...")
        token_response = Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_response
        )
        print("Token response created successfully")
        
        print(f"Final response: {token_response.dict()}")
        return True
        
    except Exception as e:
        print(f"Registration failed with error: {str(e)}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    success = test_full_registration()
    if success:
        print("\nFull registration test PASSED")
    else:
        print("\nFull registration test FAILED")