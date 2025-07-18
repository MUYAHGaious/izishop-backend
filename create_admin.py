#!/usr/bin/env python3
"""
Script to create admin users for IziShopin backend
Usage: python create_admin.py
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

def create_admin_user():
    """Create an admin user interactively"""
    print("🔧 IziShopin Admin User Creation")
    print("=" * 40)
    
    # Get database session
    db = next(get_db())
    
    try:
        # Ensure tables exist
        create_tables()
        
        print("📧 Enter admin details:")
        email = input("Email: ").strip()
        
        # Check if admin already exists
        existing_user = get_user_by_email(db, email)
        if existing_user:
            print(f"❌ User with email {email} already exists!")
            if existing_user.role == UserRole.ADMIN:
                print("✅ This user is already an admin.")
            else:
                print(f"ℹ️  This user exists with role: {existing_user.role}")
            return
        
        # Get password (simple input for now)
        password = input("Password: ").strip()
        if len(password) < 8:
            print("❌ Password must be at least 8 characters long!")
            return
        
        first_name = input("First Name: ").strip()
        last_name = input("Last Name: ").strip()
        phone = input("Phone (optional): ").strip() or None
        
        # Create admin user
        print("\n🔨 Creating admin user...")
        
        user = create_user(
            db=db,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=UserRole.ADMIN,
            phone=phone
        )
        
        print(f"✅ Admin user created successfully!")
        print(f"📧 Email: {user.email}")
        print(f"👤 Name: {user.first_name} {user.last_name}")
        print(f"🔑 Role: {user.role}")
        print(f"📅 Created: {user.created_at}")
        print(f"🆔 ID: {user.id}")
        
        print("\n🎉 Admin user creation complete!")
        print("You can now login at: http://localhost:3000/admin-login")
        
    except Exception as e:
        print(f"❌ Error creating admin user: {str(e)}")
        db.rollback()
    finally:
        db.close()

def list_admin_users():
    """List all admin users"""
    print("👥 Current Admin Users")
    print("=" * 40)
    
    db = next(get_db())
    
    try:
        from models.user import User
        
        admins = db.query(User).filter(User.role == UserRole.ADMIN).all()
        
        if not admins:
            print("No admin users found.")
            return
        
        for admin in admins:
            print(f"📧 {admin.email}")
            print(f"👤 {admin.first_name} {admin.last_name}")
            print(f"📅 Created: {admin.created_at}")
            print(f"🔍 Active: {admin.is_active}")
            print(f"✅ Verified: {admin.is_verified}")
            print("-" * 30)
            
    except Exception as e:
        print(f"❌ Error listing admin users: {str(e)}")
    finally:
        db.close()

def main():
    """Main function"""
    print("🚀 IziShopin Admin Management")
    print("=" * 40)
    print("1. Create Admin User")
    print("2. List Admin Users")
    print("3. Exit")
    
    while True:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == "1":
            create_admin_user()
            break
        elif choice == "2":
            list_admin_users()
            break
        elif choice == "3":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please select 1, 2, or 3.")

if __name__ == "__main__":
    main()