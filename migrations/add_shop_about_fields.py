#!/usr/bin/env python3
"""
Migration script to add about section fields to existing shops
Run this script to update existing shops with default values for new fields
"""

import sys
import os
import json
from datetime import datetime

# Add the parent directory to the path so we can import our models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_db
from models.shop import Shop
from sqlalchemy.orm import Session

def migrate_shop_about_fields():
    """Add default values for new about section fields to existing shops"""
    
    db = next(get_db())
    
    try:
        print("Starting migration: Adding about section fields to existing shops...")
        
        # Get all existing shops
        shops = db.query(Shop).all()
        print(f"Found {len(shops)} shops to update")
        
        # Default values for new fields
        default_business_hours = {
            "monday": "9:00 AM - 6:00 PM",
            "tuesday": "9:00 AM - 6:00 PM", 
            "wednesday": "9:00 AM - 6:00 PM",
            "thursday": "9:00 AM - 6:00 PM",
            "friday": "9:00 AM - 6:00 PM",
            "saturday": "10:00 AM - 4:00 PM",
            "sunday": "Closed"
        }
        
        default_policies = {
            "return_policy": "30-day return policy for all items in original condition with receipt.",
            "shipping_policy": "Free shipping on orders over 50,000 XAF. Standard delivery 2-5 business days.",
            "warranty": "All electronics come with manufacturer warranty. Extended warranty available.",
            "customer_support": "24/7 customer support via chat, email, or phone. Average response time: 2 hours."
        }
        
        default_team_members = [
            {
                "name": "Shop Owner",
                "role": "Founder & CEO",
                "experience": "5+ years in retail",
                "image": None
            }
        ]
        
        default_milestones = [
            {
                "year": "2024",
                "title": "Shop Founded",
                "description": "Started our journey with a vision to provide quality products",
                "icon": "Package"
            }
        ]
        
        default_certifications = []
        
        default_coordinates = {
            "lat": 0.0,
            "lng": 0.0
        }
        
        updated_count = 0
        
        for shop in shops:
            # Only update if fields are None or empty
            updates = {}
            
            if not shop.mission:
                updates['mission'] = f"Our mission is to deliver high-quality products that enhance our customers' lives while building lasting relationships based on trust and excellence."
            
            if not shop.vision:
                updates['vision'] = f"We envision becoming the go-to destination for customers seeking reliable products and outstanding service in our region."
            
            if not shop.business_hours:
                updates['business_hours'] = json.dumps(default_business_hours)
            
            if not shop.policies:
                updates['policies'] = json.dumps(default_policies)
            
            if not shop.team_members:
                updates['team_members'] = json.dumps(default_team_members)
            
            if not shop.milestones:
                updates['milestones'] = json.dumps(default_milestones)
            
            if not shop.certifications:
                updates['certifications'] = json.dumps(default_certifications)
            
            if not shop.coordinates:
                updates['coordinates'] = json.dumps(default_coordinates)
            
            if not shop.followers_count:
                updates['followers_count'] = 0
            
            if not shop.product_count:
                updates['product_count'] = 0
            
            if not shop.total_sales:
                updates['total_sales'] = 0.0
            
            # Apply updates if any
            if updates:
                for field, value in updates.items():
                    setattr(shop, field, value)
                
                shop.updated_at = datetime.utcnow()
                updated_count += 1
                print(f"Updated shop: {shop.name} (ID: {shop.id})")
        
        # Commit all changes
        db.commit()
        print(f"\nMigration completed successfully!")
        print(f"Updated {updated_count} shops with default about section data")
        
    except Exception as e:
        print(f"Migration failed: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_shop_about_fields()
