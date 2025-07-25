#!/usr/bin/env python3
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

from database.base import Base
from database.session import engine
from models import user, wallet, shop, category, product, order, payment, delivery, rating

def create_all_tables():
    """Create all database tables"""
    try:
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ All tables created successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        return False

if __name__ == "__main__":
    success = create_all_tables()
    sys.exit(0 if success else 1)