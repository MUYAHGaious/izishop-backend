"""
Notification Service for IziShop Role Upgrade System
Implements comprehensive notification management with event integration
"""

from typing import Dict, Any, List, Optional, Union
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
import logging

from models.notification import (
    Notification, 
    NotificationPreference, 
    NotificationTemplate,
    NotificationType, 
    NotificationPriority, 
    NotificationStatus
)
from models.user import User
from core.event_system import SystemEvent, EventType, event_handler

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for managing system notifications"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def create_notification(
        self,
        user_id: UUID,
        title: str,
        message: str,
        notification_type: NotificationType,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        action_url: Optional[str] = None,
        action_label: Optional[str] = None,
        icon: Optional[str] = None,
        related_id: Optional[str] = None,
        related_type: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Notification:
        """Create a new notification"""
        
        notification = Notification(
            user_id=str(user_id),
            title=title,
            message=message,
            type=notification_type,
            priority=priority,
            action_url=action_url,
            action_label=action_label,
            icon=icon,
            related_id=related_id,
            related_type=related_type,
            expires_at=expires_at
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        logger.info(f"Created notification {notification.id} for user {user_id}")
        return notification
    
    async def create_role_upgrade_notification(
        self,
        user_id: UUID,
        old_role: str,
        new_role: str
    ) -> Notification:
        """Create notification for successful role upgrade"""
        
        # Role-specific messaging
        role_messages = {
            "SHOP_OWNER": {
                "title": "🎉 Welcome to Shop Owner!",
                "message": f"Congratulations! You've been upgraded from {old_role} to {new_role}. You can now create and manage your own shop, add products, and start selling on IziShop!",
                "icon": "crown",
                "action_url": "/shop-owner-dashboard",
                "action_label": "Go to Dashboard"
            },
            "DELIVERY_AGENT": {
                "title": "🚚 Welcome to Delivery Team!",
                "message": f"You've been upgraded from {old_role} to {new_role}. You can now accept and manage delivery orders in your area.",
                "icon": "truck",
                "action_url": "/delivery-agent-dashboard",
                "action_label": "Go to Dashboard"
            },
            "ADMIN": {
                "title": "⚡ Admin Access Granted",
                "message": f"You've been granted {new_role} privileges. You now have full system access.",
                "icon": "shield",
                "action_url": "/admin-dashboard",
                "action_label": "Go to Admin Panel"
            }
        }
        
        config = role_messages.get(new_role, {
            "title": f"Role Updated to {new_role}",
            "message": f"Your role has been changed from {old_role} to {new_role}.",
            "icon": "user-check",
            "action_url": "/profile",
            "action_label": "View Profile"
        })
        
        return await self.create_notification(
            user_id=user_id,
            title=config["title"],
            message=config["message"],
            notification_type=NotificationType.SYSTEM,
            priority=NotificationPriority.HIGH,
            action_url=config["action_url"],
            action_label=config["action_label"],
            icon=config["icon"],
            related_id=str(user_id),
            related_type="role_upgrade"
        )
    
    async def create_shop_created_notification(
        self,
        user_id: UUID,
        shop_id: UUID,
        shop_name: str
    ) -> Notification:
        """Create notification for shop creation"""
        
        return await self.create_notification(
            user_id=user_id,
            title="🏪 Your Shop is Ready!",
            message=f"Your shop '{shop_name}' has been created successfully! You can now start adding products and managing your inventory.",
            notification_type=NotificationType.SHOP,
            priority=NotificationPriority.HIGH,
            action_url=f"/shop/{shop_id}",
            action_label="Manage Shop",
            icon="store",
            related_id=str(shop_id),
            related_type="shop"
        )
    
    async def create_role_upgrade_failed_notification(
        self,
        user_id: UUID,
        target_role: str,
        reason: str
    ) -> Notification:
        """Create notification for failed role upgrade"""
        
        return await self.create_notification(
            user_id=user_id,
            title="❌ Role Upgrade Failed",
            message=f"We couldn't upgrade your role to {target_role}. Reason: {reason}. Please contact support if you need assistance.",
            notification_type=NotificationType.SYSTEM,
            priority=NotificationPriority.HIGH,
            action_url="/help",
            action_label="Get Help",
            icon="alert-circle",
            related_id=str(user_id),
            related_type="role_upgrade_failed"
        )
    
    async def get_user_notifications(
        self,
        user_id: UUID,
        status: Optional[NotificationStatus] = None,
        notification_type: Optional[NotificationType] = None,
        limit: int = 20,
        offset: int = 0,
        include_expired: bool = False
    ) -> Dict[str, Any]:
        """Get notifications for a user"""
        
        query = self.db.query(Notification).filter(
            Notification.user_id == str(user_id)
        )
        
        # Filter by status
        if status:
            if status == NotificationStatus.UNREAD:
                query = query.filter(Notification.is_read == False)
            elif status == NotificationStatus.READ:
                query = query.filter(Notification.is_read == True)
            elif status == NotificationStatus.ARCHIVED:
                query = query.filter(Notification.status == NotificationStatus.ARCHIVED)
        
        # Filter by type
        if notification_type:
            query = query.filter(Notification.type == notification_type)
        
        # Filter expired notifications
        if not include_expired:
            query = query.filter(
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination and ordering
        notifications = query.order_by(desc(Notification.created_at))\
                           .offset(offset)\
                           .limit(limit)\
                           .all()
        
        # Get unread count
        unread_count = self.db.query(Notification).filter(
            and_(
                Notification.user_id == str(user_id),
                Notification.is_read == False,
                or_(
                    Notification.expires_at.is_(None),
                    Notification.expires_at > datetime.utcnow()
                )
            )
        ).count()
        
        return {
            "notifications": [self._notification_to_dict(n) for n in notifications],
            "total_count": total_count,
            "unread_count": unread_count,
            "has_more": (offset + limit) < total_count
        }
    
    async def mark_as_read(
        self,
        notification_id: str,
        user_id: UUID
    ) -> bool:
        """Mark a notification as read"""
        
        notification = self.db.query(Notification).filter(
            and_(
                Notification.id == notification_id,
                Notification.user_id == str(user_id)
            )
        ).first()
        
        if not notification:
            return False
        
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            notification.status = NotificationStatus.READ
            self.db.commit()
            
            logger.info(f"Marked notification {notification_id} as read for user {user_id}")
        
        return True
    
    async def mark_as_archived(
        self,
        notification_id: str,
        user_id: UUID
    ) -> bool:
        """Mark a notification as archived"""
        
        notification = self.db.query(Notification).filter(
            and_(
                Notification.id == notification_id,
                Notification.user_id == str(user_id)
            )
        ).first()
        
        if not notification:
            return False
        
        notification.status = NotificationStatus.ARCHIVED
        notification.is_read = True
        if not notification.read_at:
            notification.read_at = datetime.utcnow()
        
        self.db.commit()
        logger.info(f"Archived notification {notification_id} for user {user_id}")
        
        return True
    
    async def mark_all_as_read(self, user_id: UUID) -> int:
        """Mark all notifications as read for a user"""
        
        count = self.db.query(Notification).filter(
            and_(
                Notification.user_id == str(user_id),
                Notification.is_read == False
            )
        ).update({
            "is_read": True,
            "read_at": datetime.utcnow(),
            "status": NotificationStatus.READ
        })
        
        self.db.commit()
        logger.info(f"Marked {count} notifications as read for user {user_id}")
        
        return count
    
    async def delete_expired_notifications(self) -> int:
        """Delete expired notifications"""
        
        count = self.db.query(Notification).filter(
            and_(
                Notification.expires_at.isnot(None),
                Notification.expires_at < datetime.utcnow()
            )
        ).delete()
        
        self.db.commit()
        logger.info(f"Deleted {count} expired notifications")
        
        return count
    
    async def delete_old_notifications(self, days: int = 30) -> int:
        """Delete notifications older than specified days"""
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # Delete old archived notifications
        archived_count = self.db.query(Notification).filter(
            and_(
                Notification.status == NotificationStatus.ARCHIVED,
                Notification.created_at < cutoff_date
            )
        ).delete()
        
        # Delete old read notifications (older than 30 days)
        read_count = self.db.query(Notification).filter(
            and_(
                Notification.is_read == True,
                Notification.created_at < cutoff_date
            )
        ).delete()
        
        self.db.commit()
        total_deleted = archived_count + read_count
        logger.info(f"Deleted {total_deleted} old notifications ({archived_count} archived, {read_count} read) older than {days} days")
        
        return total_deleted
    
    async def cleanup_notifications(self) -> Dict[str, int]:
        """Run complete notification cleanup - expired and old notifications"""
        
        expired_count = await self.delete_expired_notifications()
        old_count = await self.delete_old_notifications(30)
        
        return {
            "expired_deleted": expired_count,
            "old_deleted": old_count,
            "total_deleted": expired_count + old_count
        }
    
    def _notification_to_dict(self, notification: Notification) -> Dict[str, Any]:
        """Convert notification to dictionary"""
        return {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "type": notification.type.value if notification.type else None,
            "priority": notification.priority.value if notification.priority else None,
            "status": notification.status.value if notification.status else "unread",
            "is_read": notification.is_read,
            "action_url": notification.action_url,
            "action_label": notification.action_label,
            "icon": notification.icon,
            "image_url": notification.image_url,
            "related_id": notification.related_id,
            "related_type": notification.related_type,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
            "expires_at": notification.expires_at.isoformat() if notification.expires_at else None,
            "clicked_at": notification.clicked_at.isoformat() if notification.clicked_at else None,
        }

# Event handlers for automatic notification creation
@event_handler(EventType.ROLE_UPGRADED)
async def handle_role_upgrade_notification(event: SystemEvent):
    """Handle role upgrade events by creating notifications"""
    from database import get_db
    
    db = next(get_db())
    notification_service = NotificationService(db)
    
    try:
        user_id = UUID(event.data["user_id"])
        old_role = event.data["old_role"]
        new_role = event.data["new_role"]
        
        await notification_service.create_role_upgrade_notification(
            user_id=user_id,
            old_role=old_role,
            new_role=new_role
        )
        
        logger.info(f"Created role upgrade notification for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to create role upgrade notification: {e}")
    finally:
        db.close()

@event_handler(EventType.ROLE_UPGRADE_FAILED)
async def handle_role_upgrade_failed_notification(event: SystemEvent):
    """Handle failed role upgrade events"""
    from database import get_db
    
    db = next(get_db())
    notification_service = NotificationService(db)
    
    try:
        user_id = UUID(event.data["user_id"])
        target_role = event.data["target_role"]
        reason = event.data.get("reason", "Unknown error")
        
        await notification_service.create_role_upgrade_failed_notification(
            user_id=user_id,
            target_role=target_role,
            reason=reason
        )
        
        logger.info(f"Created role upgrade failed notification for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to create role upgrade failed notification: {e}")
    finally:
        db.close()

@event_handler(EventType.SHOP_CREATED)
async def handle_shop_created_notification(event: SystemEvent):
    """Handle shop creation events"""
    from database import get_db
    
    db = next(get_db())
    notification_service = NotificationService(db)
    
    try:
        user_id = UUID(event.data["owner_id"])
        shop_id = UUID(event.data["shop_id"])
        shop_name = event.data["shop_name"]
        
        await notification_service.create_shop_created_notification(
            user_id=user_id,
            shop_id=shop_id,
            shop_name=shop_name
        )
        
        logger.info(f"Created shop creation notification for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to create shop creation notification: {e}")
    finally:
        db.close()