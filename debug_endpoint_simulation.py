#!/usr/bin/env python3
"""Debug script to simulate exactly what the endpoint does."""

import sys
sys.path.append('.')

from sqlalchemy.orm import Session
from database.connection import get_db, create_tables
from services.auth import create_user, create_access_token, create_refresh_token
from models.user import UserRole
from schemas.user import UserResponse, Token, UserRegister
from datetime import timedelta
from core.config import settings
import traceback
import uuid

def simulate_endpoint():
    """Simulate the exact endpoint call."""
    print("Simulating endpoint call...")
    
    try:
        # Create tables first
        create_tables()
        
        # Get database session
        db = next(get_db())
        
        # Simulate user_data input
        unique_id = str(uuid.uuid4())[:8]
        email = f"endpoint_{unique_id}@example.com"
        
        user_data = UserRegister(
            email=email,
            password="testpassword123",
            confirm_password="testpassword123",
            first_name="Endpoint",
            last_name="Test",
            role="CUSTOMER",
            phone="2222222222"
        )
        
        print(f"UserRegister created: {user_data.email}")
        
        # Check passwords match
        if user_data.password != user_data.confirm_password:
            raise ValueError("Passwords do not match")
        print("Password check passed")

        # Create the user
        print("Creating user...")
        user = create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            phone=user_data.phone
        )
        print(f"User created: {user.email}")

        # Create access token and refresh token
        print("Creating tokens...")
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id)},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )
        print("Tokens created")

        # Use model_validate instead of from_orm (Pydantic v2 compatibility)
        print("Creating UserResponse...")
        user_response = UserResponse.model_validate(user)
        print("UserResponse created")

        print("Creating Token response...")
        token_response = Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_response
        )
        print("Token response created")
        
        print("SUCCESS: Registration simulation completed")
        return True
        
    except Exception as e:
        print(f"FAILED: Registration simulation failed with error: {str(e)}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    success = simulate_endpoint()
    if success:
        print("\nEndpoint simulation PASSED")
    else:
        print("\nEndpoint simulation FAILED")