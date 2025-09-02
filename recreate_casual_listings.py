#!/usr/bin/env python3
"""Script to recreate casual_listings table with correct schema."""

import sys
sys.path.append('.')

from sqlalchemy import text
from database.connection import engine
from models.casual_listing import CasualListing

def recreate_casual_listings_table():
    """Drop and recreate the casual_listings table."""
    print("Recreating casual_listings table...")
    
    try:
        with engine.connect() as conn:
            # Drop existing table
            print("Dropping existing casual_listings table...")
            conn.execute(text("DROP TABLE IF EXISTS casual_listings"))
            
            # Create new table with correct schema
            print("Creating new casual_listings table...")
            CasualListing.__table__.create(engine)
            
            conn.commit()
            
        print("Casual listings table recreated successfully!")
        return True
        
    except Exception as e:
        print(f"Error recreating table: {str(e)}")
        return False

if __name__ == "__main__":
    success = recreate_casual_listings_table()
    if success:
        print("\nTable recreation PASSED")
    else:
        print("\nTable recreation FAILED")