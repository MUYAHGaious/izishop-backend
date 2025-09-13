"""
Batch Operations Router
Provides API endpoints for batch processing operations
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from core.batch_system import BatchConfig, BatchOperationType, BatchStatus
from core.batch_processors.notification_batch import (
    batch_create_notifications,
    batch_delete_old_notifications
)
from core.batch_processors.product_batch import (
    batch_create_products,
    batch_update_prices
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/batch", tags=["batch"])

# Pydantic schemas
class BatchConfigRequest(BaseModel):
    batch_size: Optional[int] = 100
    max_retries: Optional[int] = 3
    retry_delay: Optional[float] = 1.0
    timeout: Optional[float] = 300.0
    parallel_workers: Optional[int] = 5
    fail_fast: Optional[bool] = False

class BatchNotificationRequest(BaseModel):
    notifications: List[Dict[str, Any]]
    config: Optional[BatchConfigRequest] = None

class BatchProductRequest(BaseModel):
    products: List[Dict[str, Any]]
    config: Optional[BatchConfigRequest] = None

class BatchPriceUpdateRequest(BaseModel):
    price_updates: List[Dict[str, Any]]
    config: Optional[BatchConfigRequest] = None

class BatchCleanupRequest(BaseModel):
    older_than_days: Optional[int] = 30
    config: Optional[BatchConfigRequest] = None

class BatchResultResponse(BaseModel):
    batch_id: str
    total_items: int
    successful: int
    failed: int
    skipped: int
    status: str
    duration: Optional[float] = None
    errors: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True

# Admin-only dependency
def verify_admin_user(current_user: UserResponse = Depends(get_current_user)):
    """Verify that the current user is an admin."""
    user_role = current_user.role.upper() if hasattr(current_user.role, 'upper') else str(current_user.role).upper()
    if user_role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required for batch operations"
        )
    return current_user

@router.post("/notifications/create", response_model=BatchResultResponse)
async def batch_create_notifications_endpoint(
    request: BatchNotificationRequest,
    background_tasks: BackgroundTasks,
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Batch create notifications (Admin only)"""
    try:
        logger.info(f"Admin {admin_user.email} initiated batch notification creation for {len(request.notifications)} items")
        
        # Convert config
        config_dict = request.config.dict() if request.config else {}
        
        # Process batch
        result = await batch_create_notifications(
            db, 
            request.notifications, 
            config_dict
        )
        
        logger.info(f"Batch notification creation completed: {result.successful} successful, {result.failed} failed")
        
        return BatchResultResponse(
            batch_id=result.batch_id,
            total_items=result.total_items,
            successful=result.successful,
            failed=result.failed,
            skipped=result.skipped,
            status=result.status.value,
            duration=result.duration,
            errors=result.errors
        )
        
    except Exception as e:
        logger.error(f"Error in batch notification creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch operation failed: {str(e)}"
        )

@router.post("/notifications/cleanup", response_model=BatchResultResponse)
async def batch_cleanup_notifications_endpoint(
    request: BatchCleanupRequest,
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Batch cleanup old notifications (Admin only)"""
    try:
        logger.info(f"Admin {admin_user.email} initiated notification cleanup for items older than {request.older_than_days} days")
        
        # Convert config
        config_dict = request.config.dict() if request.config else {}
        
        # Process batch cleanup
        result = await batch_delete_old_notifications(
            db,
            request.older_than_days,
            config_dict
        )
        
        logger.info(f"Batch notification cleanup completed: {result.successful} successful, {result.failed} failed")
        
        return BatchResultResponse(
            batch_id=result.batch_id,
            total_items=result.total_items,
            successful=result.successful,
            failed=result.failed,
            skipped=result.skipped,
            status=result.status.value if hasattr(result.status, 'value') else result.status,
            duration=result.duration,
            errors=result.errors
        )
        
    except Exception as e:
        logger.error(f"Error in batch notification cleanup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch cleanup failed: {str(e)}"
        )

@router.post("/products/create", response_model=BatchResultResponse)
async def batch_create_products_endpoint(
    request: BatchProductRequest,
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Batch create products (Admin only)"""
    try:
        logger.info(f"Admin {admin_user.email} initiated batch product creation for {len(request.products)} items")
        
        # Convert config
        config_dict = request.config.dict() if request.config else {}
        
        # Process batch
        result = await batch_create_products(
            db,
            request.products,
            config_dict
        )
        
        logger.info(f"Batch product creation completed: {result.successful} successful, {result.failed} failed")
        
        return BatchResultResponse(
            batch_id=result.batch_id,
            total_items=result.total_items,
            successful=result.successful,
            failed=result.failed,
            skipped=result.skipped,
            status=result.status.value,
            duration=result.duration,
            errors=result.errors
        )
        
    except Exception as e:
        logger.error(f"Error in batch product creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch operation failed: {str(e)}"
        )

@router.post("/products/update-prices", response_model=BatchResultResponse)
async def batch_update_prices_endpoint(
    request: BatchPriceUpdateRequest,
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Batch update product prices (Admin only)"""
    try:
        logger.info(f"Admin {admin_user.email} initiated batch price update for {len(request.price_updates)} items")
        
        # Convert config
        config_dict = request.config.dict() if request.config else {}
        
        # Process batch
        result = await batch_update_prices(
            db,
            request.price_updates,
            config_dict
        )
        
        logger.info(f"Batch price update completed: {result.successful} successful, {result.failed} failed")
        
        return BatchResultResponse(
            batch_id=result.batch_id,
            total_items=result.total_items,
            successful=result.successful,
            failed=result.failed,
            skipped=result.skipped,
            status=result.status.value,
            duration=result.duration,
            errors=result.errors
        )
        
    except Exception as e:
        logger.error(f"Error in batch price update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch operation failed: {str(e)}"
        )

@router.get("/operations/supported")
async def get_supported_batch_operations(
    admin_user: UserResponse = Depends(verify_admin_user)
):
    """Get list of supported batch operations (Admin only)"""
    return {
        "supported_operations": [
            {
                "endpoint": "/batch/notifications/create",
                "description": "Batch create notifications",
                "method": "POST",
                "entity": "notifications"
            },
            {
                "endpoint": "/batch/notifications/cleanup", 
                "description": "Batch cleanup old notifications",
                "method": "POST",
                "entity": "notifications"
            },
            {
                "endpoint": "/batch/products/create",
                "description": "Batch create products",
                "method": "POST", 
                "entity": "products"
            },
            {
                "endpoint": "/batch/products/update-prices",
                "description": "Batch update product prices",
                "method": "POST",
                "entity": "products"
            }
        ],
        "configuration_options": {
            "batch_size": "Number of items to process in each chunk (default: 100)",
            "max_retries": "Maximum number of retries for failed items (default: 3)",
            "retry_delay": "Delay between retries in seconds (default: 1.0)",
            "timeout": "Timeout per item in seconds (default: 300.0)",
            "parallel_workers": "Number of parallel workers (default: 5)",
            "fail_fast": "Stop on first error (default: false)"
        }
    }

@router.get("/config/defaults")
async def get_default_batch_config(
    admin_user: UserResponse = Depends(verify_admin_user)
):
    """Get default batch configuration (Admin only)"""
    config = BatchConfig()
    return {
        "default_config": {
            "batch_size": config.batch_size,
            "max_retries": config.max_retries,
            "retry_delay": config.retry_delay,
            "timeout": config.timeout,
            "parallel_workers": config.parallel_workers,
            "fail_fast": config.fail_fast,
            "validate_before_process": config.validate_before_process,
            "auto_cleanup": config.auto_cleanup,
            "cleanup_after_hours": config.cleanup_after_hours
        }
    }

# Wishlist Batch Operations

class WishlistBatchRequest(BaseModel):
    items: List[Dict[str, Any]]
    operation_type: str  # add, remove, toggle, clear, sync
    user_id: Optional[str] = None
    config: Optional[BatchConfigRequest] = None

@router.post("/wishlist/batch", response_model=BatchResultResponse)
async def batch_wishlist_operations_endpoint(
    request: WishlistBatchRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Batch wishlist operations (add, remove, toggle, clear, sync)"""
    try:
        logger.info(f"User {current_user.email} initiated batch wishlist operation: {request.operation_type}")

        from core.batch_system import UniversalBatchSystem
        from core.batch_processors.wishlist_batch import WishlistBatchProcessor

        # Use current user ID if not specified
        user_id = request.user_id or current_user.id

        # Ensure user can only modify their own wishlist (non-admin)
        if not current_user.is_admin and user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only modify your own wishlist"
            )

        # Convert config
        config_dict = request.config.dict() if request.config else {}
        batch_config = BatchConfig(**config_dict)

        # Initialize batch system
        batch_system = UniversalBatchSystem(db, batch_config)

        # Create batch processor
        processor = WishlistBatchProcessor(
            db=db,
            operation_type=request.operation_type,
            user_id=user_id
        )

        # Validate operation type
        if request.operation_type not in processor.get_supported_operations():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported operation: {request.operation_type}. Supported: {processor.get_supported_operations()}"
            )

        # Create batch with items
        batch_id = await batch_system.create_batch(
            items=request.items,
            processor=processor,
            operation_type=BatchOperationType.CUSTOM
        )

        # Process batch
        result = await batch_system.process_batch(batch_id)

        logger.info(f"Batch wishlist operation completed: {result.successful} successful, {result.failed} failed")

        return BatchResultResponse(
            batch_id=result.batch_id,
            total_items=result.total_items,
            successful=result.successful,
            failed=result.failed,
            skipped=result.skipped,
            status=result.status.value,
            duration=result.duration,
            errors=result.errors
        )

    except Exception as e:
        logger.error(f"Error in batch wishlist operation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch operation failed: {str(e)}"
        )