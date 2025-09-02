#!/usr/bin/env python3
"""Debug script to test user registration directly."""

import sys
sys.path.append('.')

from sqlalchemy.orm import Session
from database.connection import get_db, create_tables
from services.auth import create_user
from models.user import UserRole
import traceback

def test_registration():
    """Test user registration directly."""
    print("Starting registration test...")
    
    try:
        # Create tables first
        print("Creating database tables...")
        create_tables()
        print("Tables created successfully")
        
        # Get database session
        db = next(get_db())
        
        print("Creating test user...")
        user = create_user(
            db=db,
            email="newuser@example.com",
            password="testpassword123",
            first_name="New", 
            last_name="User",
            role=UserRole.CUSTOMER,
            phone="9876543210"
        )
        
        print(f"User created successfully: {user.email} with ID: {user.id}")
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
    success = test_registration()
    if success:
        print("\nRegistration test PASSED")
    else:
        print("\nRegistration test FAILED")