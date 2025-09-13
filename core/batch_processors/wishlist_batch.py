"""
Wishlist Batch Processor
Handles batch operations for wishlist management using the Universal Batch System.
"""

from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timezone
import json

from ..batch_system import BatchProcessor, BatchItem, BatchOperationType
from ...models import User, Product, Wishlist
from ...database import get_db


class WishlistBatchProcessor(BatchProcessor[Wishlist]):
    """
    Batch processor for wishlist operations.
    Supports: add, remove, clear, move_to_cart, sync operations
    """

    def __init__(self, db: Session, operation_type: str = "add", user_id: Optional[str] = None):
        self.db = db
        self.operation_type = operation_type
        self.user_id = user_id
        self.processed_items = []
        self.validation_errors = []

    async def validate_item(self, item: BatchItem) -> bool:
        """Validate individual wishlist item before processing"""
        try:
            data = item.data

            # Common validation for all operations
            if self.operation_type in ['add', 'remove', 'toggle']:
                # Validate product_id exists
                if 'product_id' not in data:
                    item.add_error("product_id is required")
                    return False

                # Check if product exists
                product = self.db.query(Product).filter(Product.id == data['product_id']).first()
                if not product:
                    item.add_error(f"Product {data['product_id']} not found")
                    return False

                # Store product for later use
                item.metadata['product'] = product

            # Validate user_id (can come from item data or processor initialization)
            user_id = data.get('user_id') or self.user_id
            if not user_id:
                item.add_error("user_id is required")
                return False

            # Check if user exists
            user = self.db.query(User).filter(User.id == user_id).first()
            if not user:
                item.add_error(f"User {user_id} not found")
                return False

            # Store user for later use
            item.metadata['user'] = user
            item.metadata['user_id'] = user_id

            # Operation-specific validation
            if self.operation_type == 'add':
                return await self._validate_add_item(item)
            elif self.operation_type == 'remove':
                return await self._validate_remove_item(item)
            elif self.operation_type == 'toggle':
                return await self._validate_toggle_item(item)
            elif self.operation_type == 'clear':
                return await self._validate_clear_item(item)
            elif self.operation_type == 'move_to_cart':
                return await self._validate_move_to_cart_item(item)
            elif self.operation_type == 'sync':
                return await self._validate_sync_item(item)

            return True

        except Exception as e:
            item.add_error(f"Validation error: {str(e)}")
            return False

    async def _validate_add_item(self, item: BatchItem) -> bool:
        """Validate add operation"""
        user_id = item.metadata['user_id']
        product_id = item.data['product_id']

        # Check if item already in wishlist
        existing = self.db.query(Wishlist).filter(
            and_(
                Wishlist.user_id == user_id,
                Wishlist.product_id == product_id
            )
        ).first()

        if existing:
            item.add_error(f"Product {product_id} already in wishlist")
            return False

        return True

    async def _validate_remove_item(self, item: BatchItem) -> bool:
        """Validate remove operation"""
        user_id = item.metadata['user_id']
        product_id = item.data['product_id']

        # Check if item exists in wishlist
        existing = self.db.query(Wishlist).filter(
            and_(
                Wishlist.user_id == user_id,
                Wishlist.product_id == product_id
            )
        ).first()

        if not existing:
            item.add_error(f"Product {product_id} not found in wishlist")
            return False

        item.metadata['existing_wishlist'] = existing
        return True

    async def _validate_toggle_item(self, item: BatchItem) -> bool:
        """Validate toggle operation"""
        user_id = item.metadata['user_id']
        product_id = item.data['product_id']

        # Check if item exists in wishlist
        existing = self.db.query(Wishlist).filter(
            and_(
                Wishlist.user_id == user_id,
                Wishlist.product_id == product_id
            )
        ).first()

        item.metadata['existing_wishlist'] = existing
        item.metadata['will_add'] = existing is None
        return True

    async def _validate_clear_item(self, item: BatchItem) -> bool:
        """Validate clear operation"""
        # Clear operation just needs a valid user_id
        return True

    async def _validate_move_to_cart_item(self, item: BatchItem) -> bool:
        """Validate move to cart operation"""
        user_id = item.metadata['user_id']
        product_id = item.data['product_id']

        # Check if item exists in wishlist
        existing = self.db.query(Wishlist).filter(
            and_(
                Wishlist.user_id == user_id,
                Wishlist.product_id == product_id
            )
        ).first()

        if not existing:
            item.add_error(f"Product {product_id} not found in wishlist")
            return False

        item.metadata['existing_wishlist'] = existing
        return True

    async def _validate_sync_item(self, item: BatchItem) -> bool:
        """Validate sync operation"""
        data = item.data

        if 'wishlist_items' not in data:
            item.add_error("wishlist_items array is required for sync operation")
            return False

        if not isinstance(data['wishlist_items'], list):
            item.add_error("wishlist_items must be an array")
            return False

        return True

    async def process_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process individual wishlist item"""
        try:
            if self.operation_type == 'add':
                return await self._process_add_item(item)
            elif self.operation_type == 'remove':
                return await self._process_remove_item(item)
            elif self.operation_type == 'toggle':
                return await self._process_toggle_item(item)
            elif self.operation_type == 'clear':
                return await self._process_clear_item(item)
            elif self.operation_type == 'move_to_cart':
                return await self._process_move_to_cart_item(item)
            elif self.operation_type == 'sync':
                return await self._process_sync_item(item)

        except Exception as e:
            item.add_error(f"Processing error: {str(e)}")
            return None

    async def _process_add_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process add operation"""
        user_id = item.metadata['user_id']
        product = item.metadata['product']

        # Create wishlist entry
        wishlist_item = Wishlist(
            user_id=user_id,
            product_id=product.id,
            added_at=datetime.now(timezone.utc),
            item_metadata=json.dumps(item.data.get('metadata', {}))
        )

        self.db.add(wishlist_item)
        item.set_result({'action': 'added', 'product_id': product.id})
        return wishlist_item

    async def _process_remove_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process remove operation"""
        existing_wishlist = item.metadata['existing_wishlist']

        self.db.delete(existing_wishlist)
        item.set_result({'action': 'removed', 'product_id': existing_wishlist.product_id})
        return existing_wishlist

    async def _process_toggle_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process toggle operation"""
        existing_wishlist = item.metadata.get('existing_wishlist')
        will_add = item.metadata['will_add']

        if will_add:
            # Add to wishlist
            user_id = item.metadata['user_id']
            product = item.metadata['product']

            wishlist_item = Wishlist(
                user_id=user_id,
                product_id=product.id,
                added_at=datetime.now(timezone.utc),
                item_metadata=json.dumps(item.data.get('metadata', {}))
            )

            self.db.add(wishlist_item)
            item.set_result({'action': 'added', 'product_id': product.id})
            return wishlist_item
        else:
            # Remove from wishlist
            self.db.delete(existing_wishlist)
            item.set_result({'action': 'removed', 'product_id': existing_wishlist.product_id})
            return existing_wishlist

    async def _process_clear_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process clear operation - removes all items for user"""
        user_id = item.metadata['user_id']

        # Get count before deletion
        count = self.db.query(Wishlist).filter(Wishlist.user_id == user_id).count()

        # Delete all wishlist items for user
        self.db.query(Wishlist).filter(Wishlist.user_id == user_id).delete()

        item.set_result({'action': 'cleared', 'items_removed': count})
        return None

    async def _process_move_to_cart_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process move to cart operation"""
        # Note: This would need integration with your cart system
        # For now, we'll just remove from wishlist
        existing_wishlist = item.metadata['existing_wishlist']

        # Here you would add logic to add to cart
        # cart_service.add_to_cart(user_id, product_id, quantity=1)

        # Remove from wishlist
        self.db.delete(existing_wishlist)
        item.set_result({
            'action': 'moved_to_cart',
            'product_id': existing_wishlist.product_id,
            'note': 'Item removed from wishlist - cart integration needed'
        })
        return existing_wishlist

    async def _process_sync_item(self, item: BatchItem) -> Optional[Wishlist]:
        """Process sync operation - synchronize frontend and backend wishlists"""
        user_id = item.metadata['user_id']
        frontend_items = item.data['wishlist_items']

        # Get current backend wishlist
        backend_items = self.db.query(Wishlist).filter(Wishlist.user_id == user_id).all()
        backend_product_ids = {item.product_id for item in backend_items}
        frontend_product_ids = {item.get('id') or item.get('product_id') for item in frontend_items if item.get('id') or item.get('product_id')}

        # Items to add (in frontend but not backend)
        to_add = frontend_product_ids - backend_product_ids
        # Items to remove (in backend but not frontend)
        to_remove = backend_product_ids - frontend_product_ids

        added_count = 0
        removed_count = 0

        # Add missing items
        for product_id in to_add:
            # Validate product exists
            product = self.db.query(Product).filter(Product.id == product_id).first()
            if product:
                wishlist_item = Wishlist(
                    user_id=user_id,
                    product_id=product_id,
                    added_at=datetime.now(timezone.utc),
                    metadata=json.dumps({'synced': True})
                )
                self.db.add(wishlist_item)
                added_count += 1

        # Remove extra items
        if to_remove:
            self.db.query(Wishlist).filter(
                and_(
                    Wishlist.user_id == user_id,
                    Wishlist.product_id.in_(to_remove)
                )
            ).delete(synchronize_session=False)
            removed_count = len(to_remove)

        item.set_result({
            'action': 'synced',
            'added': added_count,
            'removed': removed_count,
            'total_items': len(frontend_product_ids)
        })
        return None

    async def post_process(self, results: List[Any]) -> Dict[str, Any]:
        """Post-processing after batch completion"""
        try:
            # Commit all changes
            self.db.commit()

            # Calculate summary statistics
            total_processed = len([r for r in results if r is not None])

            operation_summary = {
                'operation': self.operation_type,
                'total_items_processed': total_processed,
                'user_id': self.user_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

            # Operation-specific summaries
            if self.operation_type == 'add':
                operation_summary['items_added'] = total_processed
            elif self.operation_type == 'remove':
                operation_summary['items_removed'] = total_processed
            elif self.operation_type == 'toggle':
                operation_summary['items_toggled'] = total_processed
            elif self.operation_type == 'clear':
                operation_summary['wishlists_cleared'] = total_processed
            elif self.operation_type == 'move_to_cart':
                operation_summary['items_moved_to_cart'] = total_processed
            elif self.operation_type == 'sync':
                operation_summary['wishlists_synced'] = total_processed

            return operation_summary

        except Exception as e:
            self.db.rollback()
            return {
                'error': f"Post-processing failed: {str(e)}",
                'operation': self.operation_type,
                'rollback_performed': True
            }

    def get_supported_operations(self) -> List[str]:
        """Get list of supported batch operations"""
        return ['add', 'remove', 'toggle', 'clear', 'move_to_cart', 'sync']

    def get_operation_description(self, operation: str) -> str:
        """Get human-readable description of operation"""
        descriptions = {
            'add': 'Add products to wishlist',
            'remove': 'Remove products from wishlist',
            'toggle': 'Toggle products in/out of wishlist',
            'clear': 'Clear entire wishlist for user',
            'move_to_cart': 'Move wishlist items to shopping cart',
            'sync': 'Synchronize frontend and backend wishlists'
        }
        return descriptions.get(operation, f'Unknown operation: {operation}')