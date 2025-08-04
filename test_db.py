#!/usr/bin/env python3
"""
Test script to diagnose database issues
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database.connection import create_tables, get_db
from models.user import User, UserRole
from models.shop import Shop
from services.auth import create_user
from sqlalchemy.orm import Session
import traceback

def test_database():
    """Test database creation and user creation"""
    try:
        print("1. Creating database tables...")
        create_tables()
        print("SUCCESS: Database tables created successfully")
        
        print("2. Testing database connection...")
        db = next(get_db())
        print("SUCCESS: Database connection successful")
        
        print("3. Testing user creation...")
        user = create_user(
            db=db,
            email="shop_owner@test.com",
            password="Test123!",
            first_name="Shop",
            last_name="Owner",
            role=UserRole.SHOP_OWNER
        )
        print(f"SUCCESS: User created successfully: {user.email}")
        
        db.close()
        print("SUCCESS: All tests passed!")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    test_database()