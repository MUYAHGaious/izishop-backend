"""Add delivery_cost column to orders table"""
from database.connection import engine
from sqlalchemy import text

def add_delivery_cost_column():
    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("PRAGMA table_info(orders)"))
            columns = [row[1] for row in result]

            if 'delivery_cost' in columns:
                print('[INFO] delivery_cost column already exists')
                return

            # Add the column
            conn.execute(text('ALTER TABLE orders ADD COLUMN delivery_cost REAL DEFAULT 0'))
            conn.commit()
            print('[SUCCESS] delivery_cost column added successfully')
    except Exception as e:
        print(f'[ERROR] {str(e)}')
        raise

if __name__ == '__main__':
    add_delivery_cost_column()
