"""
Usage Examples for Universal Batch System
Shows how different entities can use the batch system
"""

import asyncio
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from core.batch_system import (
    create_batch_system, 
    BatchConfig, 
    BatchOperationType,
    BatchProcessor,
    BatchItem
)
from core.batch_processors.notification_batch import (
    batch_create_notifications,
    batch_delete_old_notifications
)
from core.batch_processors.product_batch import (
    batch_create_products,
    batch_update_prices
)

# Example 1: Simple notification batch creation
async def example_notification_batch(db: Session):
    """Example of batch creating notifications"""
    
    notifications_data = [
        {
            "user_id": "user_123",
            "title": "Welcome to IziShopin!",
            "message": "Thanks for joining our marketplace",
            "type": "system",
            "priority": "medium"
        },
        {
            "user_id": "user_456", 
            "title": "Order Shipped",
            "message": "Your order #12345 has been shipped",
            "type": "order",
            "priority": "high"
        },
        {
            "user_id": "user_789",
            "title": "New Product Alert",
            "message": "Check out this amazing new product!",
            "type": "promotion",
            "priority": "low"
        }
    ]
    
    # Run batch operation
    result = await batch_create_notifications(db, notifications_data)
    
    print(f"Batch completed: {result.successful} successful, {result.failed} failed")
    return result

# Example 2: Product batch with custom configuration
async def example_product_batch_with_config(db: Session):
    """Example of batch creating products with custom config"""
    
    products_data = [
        {
            "name": "iPhone 15 Pro",
            "description": "Latest Apple smartphone",
            "price": 1200.00,
            "shop_id": "shop_123",
            "category": "Electronics",
            "stock_quantity": 50
        },
        {
            "name": "Samsung Galaxy S24",
            "description": "Premium Android phone",
            "price": 1000.00,
            "shop_id": "shop_123", 
            "category": "Electronics",
            "stock_quantity": 30
        }
    ]
    
    # Custom batch configuration
    custom_config = {
        "batch_size": 10,  # Process 10 items at a time
        "max_retries": 5,  # Retry up to 5 times
        "parallel_workers": 2,  # Use 2 parallel workers
        "fail_fast": False,  # Don't stop on first error
        "timeout": 60.0  # 60 second timeout per item
    }
    
    result = await batch_create_products(db, products_data, custom_config)
    print(f"Product batch completed: {result.successful} successful, {result.failed} failed")
    return result

# Example 3: Custom batch processor
class UserBatchProcessor(BatchProcessor):
    """Custom batch processor for user operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def validate_item(self, item: BatchItem) -> bool:
        """Validate user data"""
        data = item.data
        
        # Check required fields
        if not data.get('email') or not data.get('password'):
            item.error = "Email and password required"
            return False
        
        # Validate email format
        if '@' not in data['email']:
            item.error = "Invalid email format"
            return False
        
        return True
    
    async def process_item(self, item: BatchItem) -> Any:
        """Process user creation/update"""
        from models.user import User
        from core.security import hash_password
        
        data = item.data
        
        # Create new user
        user = User(
            email=data['email'],
            password_hash=hash_password(data['password']),
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            role=data.get('role', 'CUSTOMER'),
            is_active=True
        )
        
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        
        return {"user_id": user.id, "email": user.email}

async def example_custom_processor(db: Session):
    """Example using custom batch processor"""
    
    users_data = [
        {
            "email": "user1@example.com",
            "password": "password123",
            "first_name": "John",
            "last_name": "Doe",
            "role": "CUSTOMER"
        },
        {
            "email": "user2@example.com", 
            "password": "password456",
            "first_name": "Jane",
            "last_name": "Smith",
            "role": "SHOP_OWNER"
        }
    ]
    
    # Create batch system
    batch_system = create_batch_system(db)
    processor = UserBatchProcessor(db)
    
    # Create and process batch
    batch_id = await batch_system.create_batch(
        users_data,
        processor,
        BatchOperationType.CREATE
    )
    
    result = await batch_system.process_batch(batch_id, processor)
    print(f"User batch completed: {result.successful} successful, {result.failed} failed")
    return result

# Example 4: Bulk price update
async def example_bulk_price_update(db: Session):
    """Example of bulk updating product prices"""
    
    price_updates = [
        {
            "id": "product_123",
            "new_price": 99.99,
            "discount_percentage": 10  # Apply 10% discount
        },
        {
            "id": "product_456", 
            "new_price": 149.99,
            "discount_percentage": 15  # Apply 15% discount
        },
        {
            "id": "product_789",
            "new_price": 199.99
            # No discount
        }
    ]
    
    result = await batch_update_prices(db, price_updates)
    print(f"Price update batch completed: {result.successful} successful, {result.failed} failed")
    return result

# Example 5: Monitoring batch progress
async def example_batch_monitoring(db: Session):
    """Example of monitoring batch progress"""
    
    # Start a long-running batch
    batch_system = create_batch_system(db)
    processor = UserBatchProcessor(db)
    
    large_users_data = [
        {
            "email": f"user{i}@example.com",
            "password": f"password{i}",
            "first_name": f"User{i}",
            "role": "CUSTOMER"
        }
        for i in range(100)  # Create 100 users
    ]
    
    batch_id = await batch_system.create_batch(
        large_users_data,
        processor,
        BatchOperationType.CREATE
    )
    
    # Start processing in background
    process_task = asyncio.create_task(
        batch_system.process_batch(batch_id, processor)
    )
    
    # Monitor progress
    while not process_task.done():
        status = await batch_system.get_batch_status(batch_id)
        if status:
            print(f"Progress: {status.successful + status.failed}/{status.total_items} processed")
            print(f"Status: {status.status}")
        
        await asyncio.sleep(2)  # Check every 2 seconds
    
    # Get final result
    result = await process_task
    print(f"Final result: {result.successful} successful, {result.failed} failed")
    return result

# Example 6: Error handling and retries
class FailingProcessor(BatchProcessor):
    """Processor that fails sometimes to demonstrate error handling"""
    
    def __init__(self):
        self.fail_counter = 0
    
    async def validate_item(self, item: BatchItem) -> bool:
        return True
    
    async def process_item(self, item: BatchItem) -> Any:
        self.fail_counter += 1
        
        # Fail every 3rd item initially, then succeed on retry
        if self.fail_counter % 3 == 0 and item.retry_count == 0:
            raise Exception("Simulated failure")
        
        return {"processed": item.data, "attempts": item.retry_count + 1}
    
    async def error_handler(self, item: BatchItem, error: Exception) -> bool:
        # Always retry once
        return item.retry_count < 1

async def example_error_handling(db: Session):
    """Example demonstrating error handling and retries"""
    
    test_data = [{"item": i} for i in range(10)]
    
    batch_system = create_batch_system(db)
    processor = FailingProcessor()
    
    batch_id = await batch_system.create_batch(
        test_data,
        processor,
        BatchOperationType.CUSTOM
    )
    
    result = await batch_system.process_batch(batch_id, processor)
    
    print(f"Error handling test: {result.successful} successful, {result.failed} failed")
    print(f"Errors encountered: {len(result.errors)}")
    
    return result

# Main function to run all examples
async def run_all_examples():
    """Run all batch system examples"""
    from database.connection import get_db
    
    # Get database session
    db = next(get_db())
    
    print("=== Batch System Examples ===\\n")
    
    try:
        print("1. Notification Batch Example:")
        await example_notification_batch(db)
        print()
        
        print("2. Product Batch with Custom Config:")
        await example_product_batch_with_config(db)
        print()
        
        print("3. Custom Processor Example:")
        await example_custom_processor(db)
        print()
        
        print("4. Bulk Price Update Example:")
        await example_bulk_price_update(db)
        print()
        
        print("5. Error Handling Example:")
        await example_error_handling(db)
        print()
        
        # Skip monitoring example as it takes longer
        # print("6. Batch Monitoring Example:")
        # await example_batch_monitoring(db)
        
    finally:
        db.close()
    
    print("=== All Examples Completed ===")

if __name__ == "__main__":
    asyncio.run(run_all_examples())