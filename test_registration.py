#!/usr/bin/env python3
"""
Test registration functionality directly
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database.connection import create_tables, get_db
from schemas.user import UserRegister
from models.user import UserRole
from services.auth import create_user
import traceback

def test_registration_flow():
    """Test the complete registration flow"""
    try:
        print("1. Creating database tables...")
        create_tables()
        print("SUCCESS: Database tables created")
        
        print("2. Testing schema validation...")
        registration_data = {
            "email": "test_reg@example.com",
            "password": "Test123!",
            "confirm_password": "Test123!",
            "first_name": "Test",
            "last_name": "Registration",
            "phone": "237600000999",
            "role": "SHOP_OWNER"
        }
        
        user_data = UserRegister(**registration_data)
        print("SUCCESS: Schema validation passed")
        
        print("3. Testing password confirmation...")
        if user_data.password != user_data.confirm_password:
            raise ValueError("Password confirmation failed")
        print("SUCCESS: Password confirmation passed")
        
        print("4. Testing user creation...")
        db = next(get_db())
        
        user = create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=UserRole(user_data.role),
            phone=user_data.phone
        )
        
        print(f"SUCCESS: User created: {user.email}")
        
        print("5. Testing duplicate email...")
        try:
            duplicate_user = create_user(
                db=db,
                email=user_data.email,
                password="AnotherPassword123!",
                first_name="Another",
                last_name="User",
                role=UserRole.CUSTOMER
            )
            print("ERROR: Duplicate email should have failed!")
        except Exception as e:
            print(f"SUCCESS: Duplicate email correctly rejected: {str(e)}")
        
        db.close()
        print("SUCCESS: All registration tests passed!")
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        print("Full traceback:")
        traceback.print_exc()

if __name__ == "__main__":
    test_registration_flow()