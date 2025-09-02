#!/usr/bin/env python3
"""Simple script to create database tables."""

import sys
sys.path.append('.')

from database.connection import engine, create_tables
from database.base import Base

# Import all models so they are registered with SQLAlchemy
from models import *

def main():
    """Create all database tables."""
    print("Creating database tables...")
    try:
        create_tables()
        print("All tables created successfully!")
    except Exception as e:
        print(f"Error creating tables: {str(e)}")
        return False
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)