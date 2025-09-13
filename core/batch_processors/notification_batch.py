"""
Notification Batch Processor
Example implementation of batch system for notifications
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from core.batch_system import BatchProcessor, BatchItem, BatchResult
from models.notification import Notification, NotificationStatus, NotificationType, NotificationPriority
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class NotificationBatchProcessor(BatchProcessor[Notification]):
    """Batch processor for notification operations"""
    
    def __init__(self, db: Session, operation_type: str = "create"):
        self.db = db
        self.operation_type = operation_type
        self.notification_service = NotificationService(db)
        
    async def validate_item(self, item: BatchItem) -> bool:
        """Validate notification data"""
        try:
            data = item.data
            
            # Required fields validation
            required_fields = ['user_id', 'title', 'message', 'type']
            for field in required_fields:
                if field not in data or not data[field]:
                    item.error = f"Missing required field: {field}"
                    return False
            
            # Validate notification type
            try:
                NotificationType(data['type'])
            except ValueError:
                item.error = f"Invalid notification type: {data['type']}"
                return False
            
            # Validate priority if provided
            if 'priority' in data:
                try:
                    NotificationPriority(data['priority'])
                except ValueError:
                    item.error = f"Invalid priority: {data['priority']}"
                    return False
            
            # Validate user exists (optional - could be heavy for large batches)
            # user_exists = self.db.query(User).filter(User.id == data['user_id']).first()
            # if not user_exists:
            #     item.error = f"User not found: {data['user_id']}"
            #     return False
            
            return True
            
        except Exception as e:
            item.error = f"Validation error: {str(e)}"
            return False
    
    async def process_item(self, item: BatchItem) -> Any:
        """Process a single notification"""
        try:
            data = item.data
            
            if self.operation_type == "create":
                return await self._create_notification(data)
            elif self.operation_type == "update":
                return await self._update_notification(data)
            elif self.operation_type == "delete":
                return await self._delete_notification(data)
            elif self.operation_type == "cleanup":
                return await self._cleanup_notification(data)
            else:
                raise ValueError(f"Unsupported operation: {self.operation_type}")
                
        except Exception as e:
            logger.error(f"Error processing notification item {item.id}: {str(e)}")
            raise
    
    async def _create_notification(self, data: Dict[str, Any]) -> Notification:
        """Create a single notification"""
        notification = self.notification_service.create_notification(
            user_id=data['user_id'],
            title=data['title'],
            message=data['message'],
            notification_type=NotificationType(data['type']),
            priority=NotificationPriority(data.get('priority', 'medium')),
            action_url=data.get('action_url'),
            action_label=data.get('action_label'),
            icon=data.get('icon'),
            expires_at=data.get('expires_at')
        )
        return notification
    
    async def _update_notification(self, data: Dict[str, Any]) -> Notification:
        """Update a single notification"""
        notification_id = data.get('id') or data.get('notification_id')
        if not notification_id:
            raise ValueError("Notification ID required for update")
        
        notification = self.db.query(Notification).filter(
            Notification.id == notification_id
        ).first()
        
        if not notification:
            raise ValueError(f"Notification not found: {notification_id}")
        
        # Update fields
        for field, value in data.items():
            if field != 'id' and field != 'notification_id' and hasattr(notification, field):
                setattr(notification, field, value)
        
        notification.updated_at = datetime.utcnow()
        self.db.commit()
        return notification
    
    async def _delete_notification(self, data: Dict[str, Any]) -> bool:
        """Delete a single notification"""
        notification_id = data.get('id') or data.get('notification_id')
        if not notification_id:
            raise ValueError("Notification ID required for deletion")
        
        success = self.notification_service.delete_notification(
            notification_id, 
            data.get('user_id')
        )
        return success
    
    async def _cleanup_notification(self, data: Dict[str, Any]) -> bool:
        """Cleanup old notification"""
        notification_id = data.get('id') or data.get('notification_id')
        if not notification_id:
            raise ValueError("Notification ID required for cleanup")
        
        # Permanently delete old notification
        notification = self.db.query(Notification).filter(
            Notification.id == notification_id
        ).first()
        
        if notification:
            self.db.delete(notification)
            self.db.commit()
            return True
        return False
    
    async def pre_process_hook(self, batch_items: List[BatchItem]) -> None:
        """Hook called before processing batch"""
        logger.info(f"Starting batch processing for {len(batch_items)} notifications")
        
        # Could add pre-processing logic here like:
        # - Checking rate limits
        # - Warming up connections
        # - Pre-loading user data
    
    async def post_process_hook(self, batch_result: BatchResult) -> None:
        """Hook called after processing batch"""
        logger.info(f"Completed notification batch: {batch_result.successful} successful, {batch_result.failed} failed")
        
        # Could add post-processing logic here like:
        # - Sending summary emails
        # - Updating statistics
        # - Triggering webhooks
        
        # Update notification statistics
        try:
            # Could update some global stats here
            pass
        except Exception as e:
            logger.warning(f"Failed to update notification stats: {str(e)}")
    
    async def error_handler(self, item: BatchItem, error: Exception) -> bool:
        """Handle errors during processing"""
        error_msg = str(error)
        
        # Don't retry validation errors
        if "validation" in error_msg.lower() or "invalid" in error_msg.lower():
            return False
        
        # Don't retry if user not found
        if "not found" in error_msg.lower():
            return False
        
        # Retry for database connection issues
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            return item.retry_count < 3
        
        # Default retry logic
        return item.retry_count < 2

# Convenience functions for common notification batch operations

async def batch_create_notifications(
    db: Session, 
    notifications_data: List[Dict[str, Any]],
    batch_config: Optional[Dict[str, Any]] = None
) -> BatchResult:
    """Batch create notifications"""
    from core.batch_system import create_batch_system, BatchConfig, BatchOperationType
    
    config = BatchConfig(**(batch_config or {}))
    batch_system = create_batch_system(db, **config.__dict__)
    processor = NotificationBatchProcessor(db, "create")
    
    batch_id = await batch_system.create_batch(
        notifications_data, 
        processor, 
        BatchOperationType.CREATE
    )
    
    return await batch_system.process_batch(batch_id, processor)

async def batch_delete_old_notifications(
    db: Session,
    older_than_days: int = 30,
    batch_config: Optional[Dict[str, Any]] = None
) -> BatchResult:
    """Batch delete old notifications"""
    from core.batch_system import create_batch_system, BatchConfig, BatchOperationType
    
    # Get old notifications
    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
    old_notifications = db.query(Notification).filter(
        Notification.created_at < cutoff_date,
        Notification.status == NotificationStatus.ARCHIVED
    ).all()
    
    # Convert to batch data
    notifications_data = [
        {"notification_id": notif.id} 
        for notif in old_notifications
    ]
    
    if not notifications_data:
        # Return empty result if no notifications to delete
        result = BatchResult(
            batch_id="empty_batch",
            total_items=0,
            successful=0,
            failed=0,
            skipped=0,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration=0.0
        )
        return result
    
    config = BatchConfig(**(batch_config or {}))
    batch_system = create_batch_system(db, **config.__dict__)
    processor = NotificationBatchProcessor(db, "cleanup")
    
    batch_id = await batch_system.create_batch(
        notifications_data,
        processor,
        BatchOperationType.DELETE
    )
    
    return await batch_system.process_batch(batch_id, processor)