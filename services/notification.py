from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import json

from models.notification import (
    Notification, 
    NotificationPreference, 
    NotificationTemplate,
    NotificationBatch,
    NotificationType, 
    NotificationPriority, 
    NotificationStatus
)
from models.user import User

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create_notification(
        self,
        user_id: str,
        title: str,
        message: str,
        notification_type: NotificationType,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        icon: Optional[str] = None,
        image_url: Optional[str] = None,
        related_id: Optional[str] = None,
        related_type: Optional[str] = None,
        scheduled_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None
    ) -> Notification:
        """Create a new notification for a user."""
        try:
            notification = Notification(
                user_id=user_id,
                title=title,
                message=message,
                type=notification_type,
                priority=priority,
                action_url=action_url,
                action_label=action_label,
                icon=icon,
                image_url=image_url,
                related_id=related_id,
                related_type=related_type,
                scheduled_at=scheduled_at,
                expires_at=expires_at
            )
            
            self.db.add(notification)
            self.db.commit()
            self.db.refresh(notification)
            
            logger.info(f"Created notification {notification.id} for user {user_id}")
            return notification
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating notification: {str(e)}")
            raise

    def create_notification_from_template(
        self,
        user_id: str,
        template_name: str,
        context: Dict[str, Any],
        **kwargs
    ) -> Optional[Notification]:
        """Create notification using a template."""
        try:
            template = self.db.query(NotificationTemplate).filter(
                NotificationTemplate.name == template_name,
                NotificationTemplate.is_active == True
            ).first()
            
            if not template:
                logger.warning(f"Template {template_name} not found")
                return None
            
            # Replace placeholders in template
            title = self._render_template(template.title_template, context)
            message = self._render_template(template.message_template, context)
            action_label = self._render_template(template.action_label_template, context) if template.action_label_template else None
            
            return self.create_notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=template.type,
                priority=template.priority,
                action_label=action_label,
                icon=template.icon,
                **kwargs
            )
            
        except Exception as e:
            logger.error(f"Error creating notification from template: {str(e)}")
            return None

    def get_user_notifications(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
        notification_type: Optional[NotificationType] = None
    ) -> List[Notification]:
        """Get notifications for a user with filtering options."""
        try:
            query = self.db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.status != NotificationStatus.DELETED
            )
            
            if unread_only:
                query = query.filter(Notification.is_read == False)
            
            if notification_type:
                query = query.filter(Notification.type == notification_type)
            
            # Filter out expired notifications
            query = query.filter(
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
            
            return query.order_by(desc(Notification.created_at)).offset(offset).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error getting user notifications: {str(e)}")
            return []

    def mark_as_read(self, notification_id: str, user_id: str) -> bool:
        """Mark a notification as read."""
        try:
            notification = self.db.query(Notification).filter(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ).first()
            
            if not notification:
                return False
            
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            notification.status = NotificationStatus.READ
            
            self.db.commit()
            logger.info(f"Marked notification {notification_id} as read")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error marking notification as read: {str(e)}")
            return False

    def mark_all_as_read(self, user_id: str) -> int:
        """Mark all unread notifications as read for a user."""
        try:
            updated_count = self.db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False
            ).update({
                "is_read": True,
                "read_at": datetime.utcnow(),
                "status": NotificationStatus.READ
            })
            
            self.db.commit()
            logger.info(f"Marked {updated_count} notifications as read for user {user_id}")
            return updated_count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error marking all notifications as read: {str(e)}")
            return 0

    def delete_notification(self, notification_id: str, user_id: str) -> bool:
        """Soft delete a notification."""
        try:
            notification = self.db.query(Notification).filter(
                Notification.id == notification_id,
                Notification.user_id == user_id
            ).first()
            
            if not notification:
                return False
            
            notification.status = NotificationStatus.DELETED
            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting notification: {str(e)}")
            return False

    def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for a user."""
        try:
            return self.db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False,
                Notification.status != NotificationStatus.DELETED,
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            ).count()
        except Exception as e:
            logger.error(f"Error getting unread count: {str(e)}")
            return 0

    def get_notification_preferences(self, user_id: str) -> Optional[NotificationPreference]:
        """Get notification preferences for a user."""
        return self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id
        ).first()

    def update_notification_preferences(
        self, 
        user_id: str, 
        preferences: Dict[str, Any]
    ) -> Optional[NotificationPreference]:
        """Update notification preferences for a user."""
        try:
            pref = self.get_notification_preferences(user_id)
            
            if not pref:
                pref = NotificationPreference(user_id=user_id)
                self.db.add(pref)
            
            # Update preferences
            for key, value in preferences.items():
                if hasattr(pref, key):
                    setattr(pref, key, value)
            
            pref.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(pref)
            
            return pref
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating notification preferences: {str(e)}")
            return None

    def should_send_notification(
        self, 
        user_id: str, 
        notification_type: NotificationType,
        channel: str = "push"
    ) -> bool:
        """Check if user preferences allow sending this type of notification."""
        preferences = self.get_notification_preferences(user_id)
        if not preferences:
            return True  # Default to allow if no preferences set
        
        preference_key = f"{channel}_{notification_type.value}"
        return getattr(preferences, preference_key, True)

    def create_order_notification(self, user_id: str, order_id: str, status: str) -> Optional[Notification]:
        """Create order-related notification."""
        status_messages = {
            "confirmed": ("Order Confirmed", "Your order has been confirmed and is being processed."),
            "shipped": ("Order Shipped", "Your order is on its way! You can track its progress."),
            "delivered": ("Order Delivered", "Your order has been delivered successfully."),
            "cancelled": ("Order Cancelled", "Your order has been cancelled. Refund will be processed.")
        }
        
        if status not in status_messages:
            return None
        
        title, message = status_messages[status]
        
        return self.create_notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=NotificationType.ORDER,
            action_url=f"/my-orders/{order_id}",
            action_label="View Order",
            icon="Package",
            related_id=order_id,
            related_type="order"
        )

    def create_payment_notification(self, user_id: str, payment_id: str, status: str, amount: float) -> Optional[Notification]:
        """Create payment-related notification."""
        if status == "success":
            return self.create_notification(
                user_id=user_id,
                title="Payment Successful",
                message=f"Your payment of {amount} XAF has been processed successfully.",
                notification_type=NotificationType.PAYMENT,
                priority=NotificationPriority.HIGH,
                action_url=f"/payment/{payment_id}",
                action_label="View Receipt",
                icon="CreditCard",
                related_id=payment_id,
                related_type="payment"
            )
        elif status == "failed":
            return self.create_notification(
                user_id=user_id,
                title="Payment Failed",
                message=f"Your payment of {amount} XAF could not be processed. Please try again.",
                notification_type=NotificationType.PAYMENT,
                priority=NotificationPriority.HIGH,
                icon="AlertCircle",
                related_id=payment_id,
                related_type="payment"
            )

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """Simple template rendering with placeholder replacement."""
        if not template:
            return ""
        
        for key, value in context.items():
            placeholder = f"{{{key}}}"
            template = template.replace(placeholder, str(value))
        
        return template

    def cleanup_expired_notifications(self) -> int:
        """Clean up expired notifications."""
        try:
            deleted_count = self.db.query(Notification).filter(
                Notification.expires_at < datetime.utcnow()
            ).update({"status": NotificationStatus.DELETED})
            
            self.db.commit()
            logger.info(f"Cleaned up {deleted_count} expired notifications")
            return deleted_count
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error cleaning up expired notifications: {str(e)}")
            return 0

# Convenience functions for common notification types
def create_order_notification(db: Session, user_id: str, order_id: str, status: str):
    service = NotificationService(db)
    return service.create_order_notification(user_id, order_id, status)

def create_payment_notification(db: Session, user_id: str, payment_id: str, status: str, amount: float):
    service = NotificationService(db)
    return service.create_payment_notification(user_id, payment_id, status, amount)

def get_user_notifications(db: Session, user_id: str, limit: int = 20, offset: int = 0):
    service = NotificationService(db)
    return service.get_user_notifications(user_id, limit, offset)

def get_unread_count(db: Session, user_id: str) -> int:
    service = NotificationService(db)
    return service.get_unread_count(user_id)