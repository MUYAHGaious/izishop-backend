from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from pydantic import BaseModel

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from services.notification import NotificationService
from models.notification import NotificationType, NotificationPriority
from models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic schemas
class NotificationResponse(BaseModel):
    id: str
    title: str
    message: str
    type: str
    priority: str
    is_read: bool
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    icon: Optional[str] = None
    image_url: Optional[str] = None
    created_at: str
    read_at: Optional[str] = None

    class Config:
        from_attributes = True

class NotificationPreferencesUpdate(BaseModel):
    email_orders: Optional[bool] = None
    email_payments: Optional[bool] = None
    email_marketing: Optional[bool] = None
    email_system: Optional[bool] = None
    email_security: Optional[bool] = None
    push_orders: Optional[bool] = None
    push_payments: Optional[bool] = None
    push_marketing: Optional[bool] = None
    push_system: Optional[bool] = None
    push_security: Optional[bool] = None
    sms_orders: Optional[bool] = None
    sms_payments: Optional[bool] = None
    sms_security: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None
    timezone: Optional[str] = None

class NotificationPreferencesResponse(BaseModel):
    email_orders: bool
    email_payments: bool
    email_marketing: bool
    email_system: bool
    email_security: bool
    push_orders: bool
    push_payments: bool
    push_marketing: bool
    push_system: bool
    push_security: bool
    sms_orders: bool
    sms_payments: bool
    sms_security: bool
    quiet_hours_start: str
    quiet_hours_end: str
    timezone: str

    class Config:
        from_attributes = True

class NotificationStats(BaseModel):
    total: int
    unread: int
    by_type: dict

class CreateNotificationRequest(BaseModel):
    user_id: str
    title: str
    message: str
    type: str
    priority: str = "medium"
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[List[str]] = None
    expires_in_hours: Optional[int] = None

class UserSummary(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool

class NotificationBulkRequest(BaseModel):
    user_ids: List[str]
    title: str
    message: str
    type: str
    priority: str = "medium"
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[List[str]] = None
    expires_in_hours: Optional[int] = None

@router.get("/", response_model=List[NotificationResponse])
def get_notifications(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
    type_filter: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notifications for the current user."""
    try:
        service = NotificationService(db)
        
        notification_type = None
        if type_filter:
            try:
                notification_type = NotificationType(type_filter)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid notification type: {type_filter}"
                )
        
        notifications = service.get_user_notifications(
            user_id=current_user.id,
            limit=limit,
            offset=offset,
            unread_only=unread_only,
            notification_type=notification_type
        )
        
        return [
            NotificationResponse(
                id=notif.id,
                title=notif.title,
                message=notif.message,
                type=notif.type.value,
                priority=notif.priority.value,
                is_read=notif.is_read,
                action_url=notif.action_url,
                action_label=notif.action_label,
                icon=notif.icon,
                image_url=notif.image_url,
                created_at=notif.created_at.isoformat(),
                read_at=notif.read_at.isoformat() if notif.read_at else None
            )
            for notif in notifications
        ]
        
    except Exception as e:
        logger.error(f"Error getting notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notifications"
        )

@router.get("/stats", response_model=NotificationStats)
def get_notification_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notification statistics for the current user."""
    try:
        service = NotificationService(db)
        
        total_notifications = service.get_user_notifications(current_user.id, limit=1000)
        unread_count = service.get_unread_count(current_user.id)
        
        # Count by type
        by_type = {}
        for notif in total_notifications:
            type_name = notif.type.value
            if type_name not in by_type:
                by_type[type_name] = {"total": 0, "unread": 0}
            by_type[type_name]["total"] += 1
            if not notif.is_read:
                by_type[type_name]["unread"] += 1
        
        return NotificationStats(
            total=len(total_notifications),
            unread=unread_count,
            by_type=by_type
        )
        
    except Exception as e:
        logger.error(f"Error getting notification stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve notification statistics"
        )

@router.get("/unread-count")
def get_unread_count(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get count of unread notifications."""
    try:
        service = NotificationService(db)
        count = service.get_unread_count(current_user.id)
        return {"count": count}
        
    except Exception as e:
        logger.error(f"Error getting unread count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get unread count"
        )

@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a specific notification as read."""
    try:
        service = NotificationService(db)
        success = service.mark_as_read(notification_id, current_user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return {"message": "Notification marked as read"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking notification as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark notification as read"
        )

@router.patch("/mark-all-read")
def mark_all_notifications_read(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark all notifications as read for the current user."""
    try:
        service = NotificationService(db)
        count = service.mark_all_as_read(current_user.id)
        
        return {"message": f"Marked {count} notifications as read"}
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark all notifications as read"
        )

@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a specific notification."""
    try:
        service = NotificationService(db)
        success = service.delete_notification(notification_id, current_user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found"
            )
        
        return {"message": "Notification deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete notification"
        )

@router.delete("/clear-all")
def clear_all_notifications(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clear all notifications for the current user."""
    try:
        service = NotificationService(db)
        count = service.clear_all_notifications(current_user.id)
        
        return {"message": f"Cleared {count} notifications"}
        
    except Exception as e:
        logger.error(f"Error clearing all notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear all notifications"
        )

@router.get("/preferences", response_model=NotificationPreferencesResponse)
def get_notification_preferences(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get notification preferences for the current user."""
    try:
        service = NotificationService(db)
        preferences = service.get_notification_preferences(current_user.id)
        
        if not preferences:
            # Return default preferences
            return NotificationPreferencesResponse(
                email_orders=True,
                email_payments=True,
                email_marketing=False,
                email_system=True,
                email_security=True,
                push_orders=True,
                push_payments=True,
                push_marketing=False,
                push_system=True,
                push_security=True,
                sms_orders=False,
                sms_payments=True,
                sms_security=True,
                quiet_hours_start="22:00",
                quiet_hours_end="08:00",
                timezone="UTC"
            )
        
        return NotificationPreferencesResponse.from_orm(preferences)
        
    except Exception as e:
        logger.error(f"Error getting notification preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get notification preferences"
        )

@router.patch("/preferences", response_model=NotificationPreferencesResponse)
def update_notification_preferences(
    preferences_update: NotificationPreferencesUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update notification preferences for the current user."""
    try:
        service = NotificationService(db)
        
        # Convert to dict, excluding None values
        preferences_dict = {
            k: v for k, v in preferences_update.dict().items() 
            if v is not None
        }
        
        updated_preferences = service.update_notification_preferences(
            current_user.id, 
            preferences_dict
        )
        
        if not updated_preferences:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update preferences"
            )
        
        return NotificationPreferencesResponse.from_orm(updated_preferences)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating notification preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update notification preferences"
        )

@router.post("/create", response_model=NotificationResponse)
def create_notification_for_current_user(
    notification_request: CreateNotificationRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a notification for the current user (self-notifications like AI analytics)."""
    try:
        # Only allow creating notifications for yourself
        if notification_request.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only create notifications for yourself"
            )
        
        # Validate notification type and priority
        try:
            notification_type = NotificationType(notification_request.type)
            notification_priority = NotificationPriority(notification_request.priority)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type or priority: {str(e)}"
            )
        
        # Calculate expiration if provided
        expires_at = None
        if notification_request.expires_in_hours:
            from datetime import datetime, timedelta
            expires_at = datetime.utcnow() + timedelta(hours=notification_request.expires_in_hours)
        
        service = NotificationService(db)
        notification = service.create_notification(
            user_id=notification_request.user_id,
            title=notification_request.title,
            message=notification_request.message,
            notification_type=notification_type,
            priority=notification_priority,
            action_url=notification_request.action_url,
            action_label=notification_request.action_label,
            icon=notification_request.icon,
            expires_at=expires_at
        )
        
        return NotificationResponse(
            id=notification.id,
            title=notification.title,
            message=notification.message,
            type=notification.type.value,
            priority=notification.priority.value,
            is_read=notification.is_read,
            action_url=notification.action_url,
            action_label=notification.action_label,
            icon=notification.icon,
            image_url=notification.image_url,
            created_at=notification.created_at.isoformat(),
            read_at=notification.read_at.isoformat() if notification.read_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create notification"
        )

# Admin-only endpoints
def verify_admin_user(current_user: UserResponse = Depends(get_current_user)):
    """Verify that the current user is an admin."""
    user_role = current_user.role.upper() if hasattr(current_user.role, 'upper') else str(current_user.role).upper()
    if user_role != "ADMIN":
        logger.warning(f"Non-admin user {current_user.email} attempted to access admin endpoint. Role: {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# Debug endpoints
@router.get("/admin/debug")
def debug_admin_access(current_user: UserResponse = Depends(get_current_user)):
    """Debug endpoint to check admin access."""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "is_admin": current_user.role.upper() == "ADMIN"
    }

@router.get("/admin/test")
def test_admin_endpoint(admin_user: UserResponse = Depends(verify_admin_user)):
    """Simple test endpoint to verify admin verification works."""
    return {
        "message": "Admin access verified",
        "admin_email": admin_user.email,
        "admin_role": admin_user.role
    }

@router.get("/admin/db-test")
def test_database_connection(
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Test database connection and basic user query."""
    try:
        # Simple count query to test DB connection
        user_count = db.query(User).count()
        return {
            "message": "Database connection successful",
            "total_users": user_count,
            "admin_email": admin_user.email
        }
    except Exception as e:
        logger.error(f"Database test failed: {str(e)}")
        return {
            "message": "Database connection failed",
            "error": str(e),
            "admin_email": admin_user.email
        }

@router.get("/admin/users", response_model=List[UserSummary])
def get_users_for_notifications(
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Get users that can receive notifications (admin only)."""
    try:
        logger.info(f"Fetching users for notifications. Admin: {admin_user.email}, Search: {search}, Role: {role}, Limit: {limit}, Offset: {offset}")
        
        query = db.query(User).filter(User.is_active == True)
        
        if search:
            search_term = f"%{search}%"
            logger.info(f"Applying search filter: {search_term}")
            query = query.filter(
                (User.email.ilike(search_term)) |
                (User.first_name.ilike(search_term)) |
                (User.last_name.ilike(search_term))
            )
        
        if role:
            logger.info(f"Applying role filter: {role}")
            query = query.filter(User.role == role)
        
        users = query.offset(offset).limit(limit).all()
        logger.info(f"Found {len(users)} users matching criteria")
        
        return [
            UserSummary(
                id=user.id,
                email=user.email,
                full_name=f"{user.first_name} {user.last_name}" if user.first_name and user.last_name else user.email,
                role=user.role.value if hasattr(user.role, 'value') else str(user.role),
                is_active=user.is_active
            )
            for user in users
        ]
        
    except Exception as e:
        logger.error(f"Error getting users for notifications: {str(e)}", exc_info=True)
        # More specific error handling
        if "database" in str(e).lower() or "connection" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Database connection error. Please try again later."
            )
        elif "permission" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions to access users"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Server error: {str(e)}"
            )

@router.post("/admin/send", response_model=NotificationResponse)
def send_notification_to_user(
    notification_request: CreateNotificationRequest,
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Send a notification to a specific user (admin only)."""
    try:
        # Verify the target user exists
        target_user = db.query(User).filter(User.id == notification_request.user_id).first()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found"
            )
        
        # Validate notification type and priority
        try:
            notification_type = NotificationType(notification_request.type)
            notification_priority = NotificationPriority(notification_request.priority)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type or priority: {str(e)}"
            )
        
        # Calculate expiration if provided
        expires_at = None
        if notification_request.expires_in_hours:
            from datetime import datetime, timedelta
            expires_at = datetime.utcnow() + timedelta(hours=notification_request.expires_in_hours)
        
        service = NotificationService(db)
        notification = service.create_notification(
            user_id=notification_request.user_id,
            title=notification_request.title,
            message=notification_request.message,
            notification_type=notification_type,
            priority=notification_priority,
            action_url=notification_request.action_url,
            action_label=notification_request.action_label,
            icon=notification_request.icon,
            expires_at=expires_at
        )
        
        return NotificationResponse(
            id=notification.id,
            title=notification.title,
            message=notification.message,
            type=notification.type.value,
            priority=notification.priority.value,
            is_read=notification.is_read,
            action_url=notification.action_url,
            action_label=notification.action_label,
            icon=notification.icon,
            image_url=notification.image_url,
            created_at=notification.created_at.isoformat(),
            read_at=notification.read_at.isoformat() if notification.read_at else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending notification: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send notification"
        )

@router.post("/admin/send-bulk")
def send_bulk_notifications(
    bulk_request: NotificationBulkRequest,
    admin_user: UserResponse = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """Send notifications to multiple users (admin only)."""
    try:
        # Validate notification type and priority
        try:
            notification_type = NotificationType(bulk_request.type)
            notification_priority = NotificationPriority(bulk_request.priority)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid notification type or priority: {str(e)}"
            )
        
        # Verify all target users exist
        existing_users = db.query(User).filter(User.id.in_(bulk_request.user_ids)).all()
        existing_user_ids = {user.id for user in existing_users}
        
        if len(existing_user_ids) != len(bulk_request.user_ids):
            missing_ids = set(bulk_request.user_ids) - existing_user_ids
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Users not found: {list(missing_ids)}"
            )
        
        # Calculate expiration if provided
        expires_at = None
        if bulk_request.expires_in_hours:
            from datetime import datetime, timedelta
            expires_at = datetime.utcnow() + timedelta(hours=bulk_request.expires_in_hours)
        
        service = NotificationService(db)
        created_notifications = []
        failed_notifications = []
        
        for user_id in bulk_request.user_ids:
            try:
                notification = service.create_notification(
                    user_id=user_id,
                    title=bulk_request.title,
                    message=bulk_request.message,
                    notification_type=notification_type,
                    priority=notification_priority,
                    action_url=bulk_request.action_url,
                    action_label=bulk_request.action_label,
                    icon=bulk_request.icon,
                    expires_at=expires_at
                )
                created_notifications.append(notification.id)
            except Exception as e:
                logger.error(f"Failed to create notification for user {user_id}: {str(e)}")
                failed_notifications.append(user_id)
        
        return {
            "message": f"Sent {len(created_notifications)} notifications successfully",
            "successful": len(created_notifications),
            "failed": len(failed_notifications),
            "failed_user_ids": failed_notifications
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending bulk notifications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send bulk notifications"
        )

@router.get("/admin/types")
def get_notification_types(
    admin_user: UserResponse = Depends(verify_admin_user)
):
    """Get available notification types and priorities (admin only)."""
    return {
        "types": [{"value": t.value, "label": t.value.replace("_", " ").title()} for t in NotificationType],
        "priorities": [{"value": p.value, "label": p.value.title()} for p in NotificationPriority],
        "icons": [
            "Bell", "Info", "AlertTriangle", "CheckCircle", "XCircle", 
            "Package", "CreditCard", "User", "Settings", "Shield",
            "Store", "ShoppingBag", "TrendingUp", "Gift", "Heart"
        ]
    }