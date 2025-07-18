#!/usr/bin/env python3
"""
Quick setup script to create a default admin user
Usage: python setup_admin.py
"""

import sys
import os
from datetime import datetime

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database.connection import get_db, create_tables
from services.auth import create_user, get_user_by_email
from models.user import UserRole

def setup_default_admin():
    """Create a default admin user"""
    print("🔧 Setting up default admin user...")
    
    # Default admin credentials
    ADMIN_EMAIL = "admin@izishop.com"
    ADMIN_PASSWORD = "Admin123!"
    ADMIN_FIRST_NAME = "System"
    ADMIN_LAST_NAME = "Administrator"
    
    # Get database session
    db = next(get_db())
    
    try:
        # Ensure tables exist
        create_tables()
        
        # Check if admin already exists
        existing_user = get_user_by_email(db, ADMIN_EMAIL)
        if existing_user:
            print(f"✅ Admin user already exists: {ADMIN_EMAIL}")
            if existing_user.role == UserRole.ADMIN:
                print("✅ User is already an admin.")
            else:
                print(f"⚠️  User exists with role: {existing_user.role}")
            return existing_user
        
        # Create admin user
        print(f"🔨 Creating admin user: {ADMIN_EMAIL}")
        
        user = create_user(
            db=db,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
            first_name=ADMIN_FIRST_NAME,
            last_name=ADMIN_LAST_NAME,
            role=UserRole.ADMIN,
            phone=None
        )
        
        print(f"✅ Admin user created successfully!")
        print(f"📧 Email: {user.email}")
        print(f"🔑 Password: {ADMIN_PASSWORD}")
        print(f"👤 Name: {user.first_name} {user.last_name}")
        print(f"🆔 ID: {user.id}")
        
        print("\n🎉 Admin setup complete!")
        print("Login credentials:")
        print(f"  Email: {ADMIN_EMAIL}")
        print(f"  Password: {ADMIN_PASSWORD}")
        print("  URL: http://localhost:3000/admin-login")
        
        return user
        
    except Exception as e:
        print(f"❌ Error creating admin user: {str(e)}")
        db.rollback()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    setup_default_admin()