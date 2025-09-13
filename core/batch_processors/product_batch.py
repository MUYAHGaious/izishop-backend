"""
Product Batch Processor
Example implementation of batch system for products
"""

import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from core.batch_system import BatchProcessor, BatchItem, BatchResult
from models.product import Product
from models.user import User

logger = logging.getLogger(__name__)

class ProductBatchProcessor(BatchProcessor[Product]):
    """Batch processor for product operations"""
    
    def __init__(self, db: Session, operation_type: str = "create"):
        self.db = db
        self.operation_type = operation_type
        
    async def validate_item(self, item: BatchItem) -> bool:
        """Validate product data"""
        try:
            data = item.data
            
            if self.operation_type == "create":
                return await self._validate_create(item, data)
            elif self.operation_type == "update":
                return await self._validate_update(item, data)
            elif self.operation_type == "delete":
                return await self._validate_delete(item, data)
            elif self.operation_type == "bulk_price_update":
                return await self._validate_price_update(item, data)
            else:
                item.error = f"Unsupported operation: {self.operation_type}"
                return False
                
        except Exception as e:
            item.error = f"Validation error: {str(e)}"
            return False
    
    async def _validate_create(self, item: BatchItem, data: Dict[str, Any]) -> bool:
        """Validate product creation data"""
        required_fields = ['name', 'description', 'price', 'shop_id']
        for field in required_fields:
            if field not in data or not data[field]:
                item.error = f"Missing required field: {field}"
                return False
        
        # Validate price
        try:
            price = float(data['price'])
            if price < 0:
                item.error = "Price must be positive"
                return False
        except (ValueError, TypeError):
            item.error = "Invalid price format"
            return False
        
        # Validate shop exists
        shop_exists = self.db.query(User).filter(
            User.id == data['shop_id'],
            User.role == 'SHOP_OWNER'
        ).first()
        if not shop_exists:
            item.error = f"Shop not found: {data['shop_id']}"
            return False
        
        return True
    
    async def _validate_update(self, item: BatchItem, data: Dict[str, Any]) -> bool:
        """Validate product update data"""
        if 'id' not in data:
            item.error = "Product ID required for update"
            return False
        
        # Check if product exists
        product = self.db.query(Product).filter(Product.id == data['id']).first()
        if not product:
            item.error = f"Product not found: {data['id']}"
            return False
        
        # Validate price if provided
        if 'price' in data:
            try:
                price = float(data['price'])
                if price < 0:
                    item.error = "Price must be positive"
                    return False
            except (ValueError, TypeError):
                item.error = "Invalid price format"
                return False
        
        return True
    
    async def _validate_delete(self, item: BatchItem, data: Dict[str, Any]) -> bool:
        """Validate product deletion data"""
        if 'id' not in data:
            item.error = "Product ID required for deletion"
            return False
        
        return True
    
    async def _validate_price_update(self, item: BatchItem, data: Dict[str, Any]) -> bool:
        """Validate bulk price update data"""
        required_fields = ['id', 'new_price']
        for field in required_fields:
            if field not in data:
                item.error = f"Missing required field: {field}"
                return False
        
        # Validate price
        try:
            price = float(data['new_price'])
            if price < 0:
                item.error = "Price must be positive"
                return False
        except (ValueError, TypeError):
            item.error = "Invalid price format"
            return False
        
        return True
    
    async def process_item(self, item: BatchItem) -> Any:
        """Process a single product"""
        try:
            data = item.data
            
            if self.operation_type == "create":
                return await self._create_product(data)
            elif self.operation_type == "update":
                return await self._update_product(data)
            elif self.operation_type == "delete":
                return await self._delete_product(data)
            elif self.operation_type == "bulk_price_update":
                return await self._update_price(data)
            else:
                raise ValueError(f"Unsupported operation: {self.operation_type}")
                
        except Exception as e:
            logger.error(f"Error processing product item {item.id}: {str(e)}")
            raise
    
    async def _create_product(self, data: Dict[str, Any]) -> Product:
        """Create a single product"""
        product = Product(
            name=data['name'],
            description=data['description'],
            price=float(data['price']),
            shop_id=data['shop_id'],
            category=data.get('category'),
            stock_quantity=data.get('stock_quantity', 0),
            is_active=data.get('is_active', True),
            tags=data.get('tags', []),
            images=data.get('images', [])
        )
        
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product
    
    async def _update_product(self, data: Dict[str, Any]) -> Product:
        """Update a single product"""
        product = self.db.query(Product).filter(Product.id == data['id']).first()
        
        # Update fields
        for field, value in data.items():
            if field != 'id' and hasattr(product, field):
                if field == 'price':
                    setattr(product, field, float(value))
                else:
                    setattr(product, field, value)
        
        self.db.commit()
        return product
    
    async def _delete_product(self, data: Dict[str, Any]) -> bool:
        """Delete a single product"""
        product = self.db.query(Product).filter(Product.id == data['id']).first()
        if product:
            self.db.delete(product)
            self.db.commit()
            return True
        return False
    
    async def _update_price(self, data: Dict[str, Any]) -> Product:
        """Update product price"""
        product = self.db.query(Product).filter(Product.id == data['id']).first()
        if product:
            old_price = product.price
            product.price = float(data['new_price'])
            
            # Apply discount if provided
            if 'discount_percentage' in data:
                discount = float(data['discount_percentage']) / 100
                product.price = product.price * (1 - discount)
            
            self.db.commit()
            logger.info(f"Updated product {product.id} price from {old_price} to {product.price}")
            return product
        
        raise ValueError(f"Product not found: {data['id']}")
    
    async def pre_process_hook(self, batch_items: List[BatchItem]) -> None:
        """Hook called before processing batch"""
        logger.info(f"Starting batch processing for {len(batch_items)} products")
        
        # Could add pre-processing logic here
        if self.operation_type == "bulk_price_update":
            logger.info("Starting bulk price update operation")
    
    async def post_process_hook(self, batch_result: BatchResult) -> None:
        """Hook called after processing batch"""
        logger.info(f"Completed product batch: {batch_result.successful} successful, {batch_result.failed} failed")
        
        # Could trigger search index updates, cache invalidation, etc.
        if self.operation_type in ["create", "update", "bulk_price_update"]:
            # Trigger search index update
            logger.info("Triggering search index update for modified products")
    
    async def error_handler(self, item: BatchItem, error: Exception) -> bool:
        """Handle errors during processing"""
        error_msg = str(error)
        
        # Don't retry validation errors
        if "validation" in error_msg.lower() or "invalid" in error_msg.lower():
            return False
        
        # Don't retry if resource not found
        if "not found" in error_msg.lower():
            return False
        
        # Retry for database connection issues
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            return item.retry_count < 3
        
        # Default retry logic
        return item.retry_count < 2

# Convenience functions

async def batch_create_products(
    db: Session,
    products_data: List[Dict[str, Any]],
    batch_config: Optional[Dict[str, Any]] = None
) -> BatchResult:
    """Batch create products"""
    from core.batch_system import create_batch_system, BatchConfig, BatchOperationType
    
    config = BatchConfig(**(batch_config or {}))
    batch_system = create_batch_system(db, **config.__dict__)
    processor = ProductBatchProcessor(db, "create")
    
    batch_id = await batch_system.create_batch(
        products_data,
        processor,
        BatchOperationType.CREATE
    )
    
    return await batch_system.process_batch(batch_id, processor)

async def batch_update_prices(
    db: Session,
    price_updates: List[Dict[str, Any]],
    batch_config: Optional[Dict[str, Any]] = None
) -> BatchResult:
    """Batch update product prices"""
    from core.batch_system import create_batch_system, BatchConfig, BatchOperationType
    
    config = BatchConfig(**(batch_config or {}))
    batch_system = create_batch_system(db, **config.__dict__)
    processor = ProductBatchProcessor(db, "bulk_price_update")
    
    batch_id = await batch_system.create_batch(
        price_updates,
        processor,
        BatchOperationType.BULK_UPDATE
    )
    
    return await batch_system.process_batch(batch_id, processor)