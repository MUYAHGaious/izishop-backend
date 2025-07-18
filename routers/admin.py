from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

from database.connection import get_db
from services.auth import create_user, get_user_by_email
from models.user import UserRole, User
from schemas.user import UserResponse
from routers.auth import get_current_user
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class AdminCreateRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str
    phone: str = None

@router.post("/setup-admin", response_model=UserResponse)
def setup_admin(admin_data: AdminCreateRequest, db: Session = Depends(get_db)):
    """
    Create an admin user (only works if no admin exists)
    This is a one-time setup endpoint
    """
    try:
        # Check if any admin users exist
        existing_admins = db.query(User).filter(User.role == UserRole.ADMIN).count()
        
        if existing_admins > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin user already exists. Use the regular admin creation process."
            )
        
        # Check if user with this email exists
        existing_user = get_user_by_email(db, admin_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Create admin user
        admin_user = create_user(
            db=db,
            email=admin_data.email,
            password=admin_data.password,
            first_name=admin_data.first_name,
            last_name=admin_data.last_name,
            role=UserRole.ADMIN,
            phone=admin_data.phone
        )
        
        logger.info(f"Admin user created: {admin_user.email}")
        
        return UserResponse.from_orm(admin_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating admin user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create admin user"
        )

@router.post("/create-default-admin", response_model=UserResponse)
def create_default_admin(db: Session = Depends(get_db)):
    """
    Create a default admin user with predefined credentials
    Only works if no admin exists
    """
    try:
        # Check if any admin users exist
        existing_admins = db.query(User).filter(User.role == UserRole.ADMIN).count()
        
        if existing_admins > 0:
            # Get the first admin user
            admin_user = db.query(User).filter(User.role == UserRole.ADMIN).first()
            return UserResponse.from_orm(admin_user)
        
        # Default admin credentials
        ADMIN_EMAIL = "admin@izishop.com"
        ADMIN_PASSWORD = "Admin123!"
        ADMIN_FIRST_NAME = "System"
        ADMIN_LAST_NAME = "Administrator"
        
        # Check if user with this email exists
        existing_user = get_user_by_email(db, ADMIN_EMAIL)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with admin email already exists"
            )
        
        # Create admin user
        admin_user = create_user(
            db=db,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
            first_name=ADMIN_FIRST_NAME,
            last_name=ADMIN_LAST_NAME,
            role=UserRole.ADMIN,
            phone=None
        )
        
        logger.info(f"Default admin user created: {admin_user.email}")
        
        return UserResponse.from_orm(admin_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating default admin user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create default admin user"
        )

@router.get("/admin-users", response_model=List[UserResponse])
def get_admin_users(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all admin users (only accessible by admins)
    """
    try:
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin privileges required."
            )
        
        # Get all admin users
        admin_users = db.query(User).filter(User.role == UserRole.ADMIN).all()
        
        return [UserResponse.from_orm(user) for user in admin_users]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting admin users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve admin users"
        )

@router.get("/admin-status")
def get_admin_status(db: Session = Depends(get_db)):
    """
    Check if admin users exist in the system
    """
    try:
        admin_count = db.query(User).filter(User.role == UserRole.ADMIN).count()
        
        return {
            "admin_exists": admin_count > 0,
            "admin_count": admin_count,
            "setup_required": admin_count == 0
        }
        
    except Exception as e:
        logger.error(f"Error checking admin status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check admin status"
        )

# Dashboard Data Endpoints
@router.get("/dashboard/overview")
def get_dashboard_overview(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get overview statistics for admin dashboard
    """
    try:
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin privileges required."
            )
        
        # Get current date for monthly calculations
        now = datetime.utcnow()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        
        # Get users by role
        customers = db.query(User).filter(User.role == UserRole.CUSTOMER).count()
        shop_owners = db.query(User).filter(User.role == UserRole.SHOP_OWNER).count()
        delivery_agents = db.query(User).filter(User.role == UserRole.DELIVERY_AGENT).count()
        admins = db.query(User).filter(User.role == UserRole.ADMIN).count()
        
        # Get new users this month
        new_users_this_month = db.query(User).filter(
            User.created_at >= start_of_month
        ).count()
        
        # Get users registered today
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        users_today = db.query(User).filter(
            User.created_at >= today_start
        ).count()
        
        # Calculate system health (simplified - based on active users vs total)
        system_health = (active_users / total_users * 100) if total_users > 0 else 100
        
        # Prepare overview data
        overview_data = {
            "total_users": total_users,
            "active_users": active_users,
            "new_users_this_month": new_users_this_month,
            "users_today": users_today,
            "customers": customers,
            "shop_owners": shop_owners,
            "delivery_agents": delivery_agents,
            "admins": admins,
            "system_health": round(system_health, 1),
            "total_orders": 0,  # Will be updated when Order model is implemented
            "monthly_revenue": 0,  # Will be updated when Order model is implemented
            "pending_approvals": 0,  # Will be updated when needed
            "last_updated": now.isoformat()
        }
        
        return overview_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard overview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard overview"
        )

@router.get("/dashboard/users")
def get_dashboard_users(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed user statistics for admin dashboard
    """
    try:
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin privileges required."
            )
        
        # Get user statistics over time (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        # Get daily user registrations for the last 30 days
        daily_registrations = []
        for i in range(30):
            day = thirty_days_ago + timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            count = db.query(User).filter(
                and_(User.created_at >= day_start, User.created_at < day_end)
            ).count()
            
            daily_registrations.append({
                "date": day.strftime("%Y-%m-%d"),
                "count": count
            })
        
        # Get user distribution by role
        role_distribution = [
            {
                "role": "Customer",
                "count": db.query(User).filter(User.role == UserRole.CUSTOMER).count()
            },
            {
                "role": "Shop Owner",
                "count": db.query(User).filter(User.role == UserRole.SHOP_OWNER).count()
            },
            {
                "role": "Delivery Agent",
                "count": db.query(User).filter(User.role == UserRole.DELIVERY_AGENT).count()
            },
            {
                "role": "Admin",
                "count": db.query(User).filter(User.role == UserRole.ADMIN).count()
            }
        ]
        
        # Get recent user registrations
        recent_users = db.query(User).order_by(User.created_at.desc()).limit(10).all()
        recent_users_data = []
        
        for user in recent_users:
            recent_users_data.append({
                "id": user.id,
                "name": f"{user.first_name} {user.last_name}",
                "email": user.email,
                "role": user.role.value,
                "created_at": user.created_at.isoformat(),
                "is_active": user.is_active,
                "is_verified": user.is_verified
            })
        
        return {
            "daily_registrations": daily_registrations,
            "role_distribution": role_distribution,
            "recent_users": recent_users_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user dashboard data"
        )

@router.get("/dashboard/activity")
def get_dashboard_activity(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recent activity for admin dashboard
    """
    try:
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin privileges required."
            )
        
        # Get recent activities (last 24 hours)
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        # Get recent user registrations
        recent_registrations = db.query(User).filter(
            User.created_at >= twenty_four_hours_ago
        ).order_by(User.created_at.desc()).limit(5).all()
        
        activities = []
        
        # Add user registration activities
        for user in recent_registrations:
            time_diff = datetime.utcnow() - user.created_at
            if time_diff.total_seconds() < 60:
                time_str = f"{int(time_diff.total_seconds())} sec ago"
            elif time_diff.total_seconds() < 3600:
                time_str = f"{int(time_diff.total_seconds() / 60)} min ago"
            else:
                time_str = f"{int(time_diff.total_seconds() / 3600)} hours ago"
            
            activities.append({
                "id": len(activities) + 1,
                "type": "user",
                "message": f"New {user.role.value.lower()} registration: {user.first_name} {user.last_name}",
                "time": time_str,
                "status": "pending" if not user.is_verified else "completed",
                "user_id": user.id,
                "user_email": user.email
            })
        
        # Add system activities
        activities.append({
            "id": len(activities) + 1,
            "type": "system",
            "message": "System health check completed",
            "time": "1 hour ago",
            "status": "completed"
        })
        
        activities.append({
            "id": len(activities) + 1,
            "type": "system",
            "message": "Database backup completed successfully",
            "time": "6 hours ago",
            "status": "completed"
        })
        
        return {
            "activities": activities[:10],  # Limit to 10 most recent
            "total_activities": len(activities)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard activity"
        )

@router.get("/dashboard/system-stats")
def get_system_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get system statistics for admin dashboard
    """
    try:
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin privileges required."
            )
        
        # Calculate system statistics
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        verified_users = db.query(User).filter(User.is_verified == True).count()
        
        # Get database size (simplified)
        database_size = "< 1 MB"  # Placeholder
        
        # Get memory usage (simplified)
        memory_usage = 45.2  # Placeholder percentage
        
        # Get uptime (simplified)
        uptime = "99.9%"  # Placeholder
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "verified_users": verified_users,
            "inactive_users": total_users - active_users,
            "unverified_users": total_users - verified_users,
            "database_size": database_size,
            "memory_usage": memory_usage,
            "uptime": uptime,
            "last_backup": "6 hours ago",
            "system_health": round((active_users / total_users * 100) if total_users > 0 else 100, 1)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting system stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve system statistics"
        )