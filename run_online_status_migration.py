#!/usr/bin/env python3
"""
Run the online status migration to add the online_status table
and online status fields to the users table.
"""

import subprocess
import sys
import os

def run_migration():
    """Run the online status database migration"""
    try:
        # Change to the backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(backend_dir)
        
        print("Running online status database migration...")
        
        # Run the alembic migration
        result = subprocess.run([
            sys.executable, "-m", "alembic", "upgrade", "add_online_status"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Migration completed successfully!")
            print(result.stdout)
        else:
            print("❌ Migration failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error running migration: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()