"""
Add payment_method and payment_reference columns to orders table
"""
from sqlalchemy import create_engine, text

engine = create_engine('sqlite:///izishop.db')

with engine.connect() as conn:
    try:
        conn.execute(text('ALTER TABLE orders ADD COLUMN payment_method VARCHAR(50)'))
        print('SUCCESS: Added payment_method column')
    except Exception as e:
        print(f'WARNING: payment_method column might already exist: {e}')

    try:
        conn.execute(text('ALTER TABLE orders ADD COLUMN payment_reference VARCHAR(100)'))
        print('SUCCESS: Added payment_reference column')
    except Exception as e:
        print(f'WARNING: payment_reference column might already exist: {e}')

    conn.commit()
    print('SUCCESS: Database migration completed successfully!')
