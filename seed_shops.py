#!/usr/bin/env python3
"""
Seed script to create sample shop data for testing the shops listing page
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from database.connection import get_db, create_tables, engine
from models.user import User, UserRole
from models.shop import Shop
from schemas.user import UserRegister
from schemas.shop import ShopCreate
from services.auth import create_user
from services.shop import create_shop
import uuid
from datetime import datetime

def create_sample_shops():
    """Create sample shops for testing"""
    # Create database tables
    create_tables()
    
    # Get database session
    db = next(get_db())
    
    try:
        # Sample shop owners data
        shop_owners = [
            {
                "first_name": "Jean",
                "last_name": "Mballa",
                "email": "jean.mballa@techhub.cm",
                "password": "Password123!",
                "confirm_password": "Password123!",
                "phone": "237600000001",
                "role": UserRole.SHOP_OWNER
            },
            {
                "first_name": "Marie",
                "last_name": "Fokou",
                "email": "marie.fokou@fashionforward.cm", 
                "password": "Password123!",
                "confirm_password": "Password123!",
                "phone": "237600000002",
                "role": UserRole.SHOP_OWNER
            },
            {
                "first_name": "Paul",
                "last_name": "Nkomo",
                "email": "paul.nkomo@homegarden.cm",
                "password": "Password123!", 
                "confirm_password": "Password123!",
                "phone": "237600000003",
                "role": UserRole.SHOP_OWNER
            },
            {
                "first_name": "Alice",
                "last_name": "Tagne",
                "email": "alice.tagne@sportzone.cm",
                "password": "Password123!",
                "confirm_password": "Password123!",
                "phone": "237600000004", 
                "role": UserRole.SHOP_OWNER
            }
        ]
        
        # Sample shops data
        shops_data = [
            {
                "name": "TechHub Cameroon",
                "description": "Leading electronics and gadgets shop in Douala with the latest technology",
                "address": "Akwa, Douala, Cameroon",
                "phone": "237670000001",
                "email": "contact@techhub.cm"
            },
            {
                "name": "Fashion Forward",
                "description": "Trendy fashion and accessories for modern style conscious individuals",
                "address": "Centre-ville, Yaoundé, Cameroon", 
                "phone": "237670000002",
                "email": "info@fashionforward.cm"
            },
            {
                "name": "Home & Garden Plus",
                "description": "Quality home improvement and garden supplies for your perfect home",
                "address": "Bonanjo, Douala, Cameroon",
                "phone": "237670000003", 
                "email": "support@homegarden.cm"
            },
            {
                "name": "SportZone Douala",
                "description": "Your one-stop shop for all sporting goods and athletic equipment",
                "address": "Bonapriso, Douala, Cameroon",
                "phone": "237670000004",
                "email": "hello@sportzone.cm"
            }
        ]
        
        created_shops = []
        
        # Create shop owners and their shops
        for i, (owner_data, shop_data) in enumerate(zip(shop_owners, shops_data)):
            try:
                # Check if user already exists
                existing_user = db.query(User).filter(User.email == owner_data["email"]).first()
                
                if not existing_user:
                    # Create user using auth service
                    user = create_user(
                        db=db,
                        email=owner_data["email"],
                        password=owner_data["password"],
                        first_name=owner_data["first_name"],
                        last_name=owner_data["last_name"],
                        role=owner_data["role"],
                        phone=owner_data["phone"]
                    )
                    print(f"Created user: {user.first_name} {user.last_name}")
                else:
                    user = existing_user
                    print(f"User already exists: {user.first_name} {user.last_name}")
                
                # Check if shop already exists
                existing_shop = db.query(Shop).filter(Shop.name == shop_data["name"]).first()
                
                if not existing_shop:
                    # Create shop
                    shop_create = ShopCreate(**shop_data)
                    shop = create_shop(db=db, shop_data=shop_create, owner_id=user.id)
                    
                    # Set some shops as verified for testing
                    if i < 2:  # First 2 shops are verified
                        shop.is_verified = True
                        shop.average_rating = 4.5 + (i * 0.3)  # 4.5, 4.8
                    else:
                        shop.average_rating = 4.0 + (i * 0.2)  # 4.4, 4.6
                        
                    db.commit()
                    created_shops.append(shop)
                    print(f"Created shop: {shop.name}")
                else:
                    created_shops.append(existing_shop)
                    print(f"Shop already exists: {existing_shop.name}")
                    
            except Exception as e:
                print(f"Error creating shop {shop_data['name']}: {str(e)}")
                db.rollback()
                continue
        
        print(f"\nSuccessfully created/verified {len(created_shops)} shops!")
        
        # Print shop details
        print("\nShop Details:")
        for shop in created_shops:
            owner = db.query(User).filter(User.id == shop.owner_id).first()
            owner_name = f"{owner.first_name} {owner.last_name}" if owner else "Unknown"
            print(f"  • {shop.name} (Owner: {owner_name})")
            print(f"    - Address: {shop.address}")
            print(f"    - Verified: {'Yes' if shop.is_verified else 'No'}")
            print(f"    - Rating: {shop.average_rating}")
            print()
            
    except Exception as e:
        print(f"Error during seeding: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting shop data seeding...")
    create_sample_shops()
    print("Shop seeding completed!")