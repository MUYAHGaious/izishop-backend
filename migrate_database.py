#!/usr/bin/env python3
"""
Database migration script to add order status history tracking
"""
import sqlite3
import os
from datetime import datetime

def run_migration():
    db_path = os.path.join(os.path.dirname(__file__), 'izishop.db')

    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("Running database migration for order status history...")

        # Check if table already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='order_status_history';
        """)
        table_exists = cursor.fetchone() is not None

        if table_exists:
            print("order_status_history table already exists")
        else:
            # Create order_status_history table
            cursor.execute("""
                CREATE TABLE order_status_history (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    changed_by TEXT,
                    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    metadata_json TEXT,
                    FOREIGN KEY (order_id) REFERENCES orders (id),
                    FOREIGN KEY (changed_by) REFERENCES users (id)
                );
            """)

            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX idx_order_status_history_order_id
                ON order_status_history(order_id);
            """)

            cursor.execute("""
                CREATE INDEX idx_order_status_history_changed_at
                ON order_status_history(changed_at);
            """)

            print("Created order_status_history table with indexes")

        # Add new columns to orders table if they don't exist
        columns_to_add = [
            ("estimated_delivery_date", "DATETIME"),
            ("carrier", "TEXT"),
            ("delivery_instructions", "TEXT"),
            ("status_updated_at", "DATETIME")
        ]

        # Get existing columns
        cursor.execute("PRAGMA table_info(orders);")
        existing_columns = {row[1] for row in cursor.fetchall()}

        for column_name, column_type in columns_to_add:
            if column_name not in existing_columns:
                cursor.execute(f"""
                    ALTER TABLE orders
                    ADD COLUMN {column_name} {column_type};
                """)
                print(f"Added column {column_name} to orders table")
            else:
                print(f"Column {column_name} already exists in orders table")

        # Create index for status_updated_at if it doesn't exist
        try:
            cursor.execute("""
                CREATE INDEX idx_orders_status_updated_at
                ON orders(status_updated_at);
            """)
            print("Created index on orders.status_updated_at")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e):
                print("Index on orders.status_updated_at already exists")
            else:
                raise

        # Create initial status history for existing orders
        cursor.execute("""
            SELECT id, status FROM orders
            WHERE id NOT IN (SELECT DISTINCT order_id FROM order_status_history);
        """)
        orders_without_history = cursor.fetchall()

        if orders_without_history:
            print(f"Creating initial status history for {len(orders_without_history)} existing orders...")

            for order_id, status in orders_without_history:
                # Generate UUID for history record
                import uuid
                history_id = str(uuid.uuid4())

                cursor.execute("""
                    INSERT INTO order_status_history
                    (id, order_id, old_status, new_status, changed_at, notes)
                    VALUES (?, ?, NULL, ?, CURRENT_TIMESTAMP, 'Initial order creation')
                """, (history_id, order_id, status))

            print(f"Created initial status history for {len(orders_without_history)} orders")

        conn.commit()
        print("Database migration completed successfully!")
        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        if 'conn' in locals():
            conn.rollback()
        return False
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    success = run_migration()
    exit(0 if success else 1)