from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
import json

from database.connection import get_db
from schemas.user import UserResponse
from routers.auth import get_current_user

router = APIRouter()

# Simple in-memory notification storage (in production, use a database)
notifications_store = {}

@router.post("/")
async def create_notification(
    notification_data: Dict[str, Any],
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new notification for the current user.
    """
    try:
        user_id = current_user.id
        notification_id = notification_data.get('id', f"notif_{datetime.now().timestamp()}")
        
        # Store notification in memory (in production, save to database)
        if user_id not in notifications_store:
            notifications_store[user_id] = []
        
        notification = {
            **notification_data,
            'id': notification_id,
            'user_id': user_id,
            'created_at': datetime.now().isoformat(),
            'read': False
        }
        
        notifications_store[user_id].append(notification)
        
        # Keep only last 50 notifications per user
        if len(notifications_store[user_id]) > 50:
            notifications_store[user_id] = notifications_store[user_id][-50:]
        
        return {"success": True, "notification_id": notification_id}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create notification: {str(e)}"
        )

@router.get("/")
async def get_notifications(
    limit: int = 20,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get notifications for the current user.
    """
    try:
        user_id = current_user.id
        user_notifications = notifications_store.get(user_id, [])
        
        # Sort by creation time (newest first) and limit
        sorted_notifications = sorted(
            user_notifications, 
            key=lambda x: x.get('created_at', ''), 
            reverse=True
        )[:limit]
        
        return {
            "notifications": sorted_notifications,
            "total": len(user_notifications),
            "unread_count": len([n for n in user_notifications if not n.get('read', True)])
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get notifications: {str(e)}"
        )

@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Mark a notification as read.
    """
    try:
        user_id = current_user.id
        user_notifications = notifications_store.get(user_id, [])
        
        # Find and update the notification
        for notification in user_notifications:
            if notification.get('id') == notification_id:
                notification['read'] = True
                notification['read_at'] = datetime.now().isoformat()
                return {"success": True}
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mark notification as read: {str(e)}"
        )

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a notification.
    """
    try:
        user_id = current_user.id
        user_notifications = notifications_store.get(user_id, [])
        
        # Find and remove the notification
        notifications_store[user_id] = [
            n for n in user_notifications 
            if n.get('id') != notification_id
        ]
        
        return {"success": True}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete notification: {str(e)}"
        )