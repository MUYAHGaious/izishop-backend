from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from models.user import User, UserRole
from schemas.user import (
    UserResponse, 
    UserProfileUpdate, 
    PasswordChange
)
from services.auth_service import AuthService
from services.user_service import UserService
from database.session import get_db
import logging

logger = logging.getLogger(__name__)

# Create router
user_router = APIRouter(prefix="/users", tags=["User Management"])

# Initialize services
auth_service = AuthService()
user_service = UserService()

@user_router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: UserResponse = Depends(auth_service.get_current_user)
):
    """Get current user's profile information."""
    return current_user

@user_router.put("/me", response_model=UserResponse)
async def update_current_user_profile(
    profile_update: UserProfileUpdate,
    current_user: UserResponse = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile information."""
    try:
        updated_user = user_service.update_user_profile(
            db=db,
            user_id=current_user.id,
            profile_update=profile_update
        )
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during profile update"
        )

@user_router.post("/me/change-password")
async def change_current_user_password(
    password_change: PasswordChange,
    current_user: UserResponse = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db)
):
    """Change current user's password."""
    try:
        success = user_service.change_password(
            db=db,
            user_id=current_user.id,
            password_change=password_change
        )
        
        if success:
            return {"message": "Password changed successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to change password"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error changing password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during password change"
        )

@user_router.get("/{user_id}", response_model=UserResponse)
async def get_user_by_id(
    user_id: str,
    current_user: UserResponse = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db)
):
    """Get user information by ID (admin only)."""
    try:
        # Check if current user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        user = user_service.get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserResponse.from_orm(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@user_router.get("/", response_model=List[UserResponse])
async def get_users(
    skip: int = Query(0, ge=0, description="Number of users to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of users to return"),
    role: Optional[UserRole] = Query(None, description="Filter users by role"),
    current_user: UserResponse = Depends(auth_service.get_admin_user),
    db: Session = Depends(get_db)
):
    """Get users with pagination and optional role filtering (admin only)."""
    try:
        if role:
            users = user_service.get_users_by_role(db, role, skip, limit)
        else:
            users = user_service.get_all_users(db, skip, limit)
        
        return [UserResponse.from_orm(user) for user in users]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@user_router.get("/search/", response_model=List[UserResponse])
async def search_users(
    query: str = Query(..., min_length=2, description="Search query for user names or emails"),
    role: Optional[UserRole] = Query(None, description="Filter users by role"),
    skip: int = Query(0, ge=0, description="Number of users to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of users to return"),
    current_user: UserResponse = Depends(auth_service.get_admin_user),
    db: Session = Depends(get_db)
):
    """Search users by name or email with optional role filtering (admin only)."""
    try:
        users = user_service.search_users(db, query, role, skip, limit)
        return [UserResponse.from_orm(user) for user in users]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@user_router.post("/{user_id}/activate")
async def activate_user(
    user_id: str,
    current_user: UserResponse = Depends(auth_service.get_admin_user),
    db: Session = Depends(get_db)
):
    """Activate a user account (admin only)."""
    try:
        success = user_service.activate_user(db, user_id)
        
        if success:
            return {"message": "User activated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to activate user"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@user_router.post("/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    current_user: UserResponse = Depends(auth_service.get_admin_user),
    db: Session = Depends(get_db)
):
    """Deactivate a user account (admin only)."""
    try:
        success = user_service.deactivate_user(db, user_id)
        
        if success:
            return {"message": "User deactivated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to deactivate user"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@user_router.get("/statistics/overview")
async def get_user_statistics(
    current_user: UserResponse = Depends(auth_service.get_admin_user),
    db: Session = Depends(get_db)
):
    """Get user statistics overview (admin only)."""
    try:
        stats = user_service.get_user_statistics(db)
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@user_router.post("/verify-email/{verification_token}")
async def verify_user_email(
    verification_token: str,
    db: Session = Depends(get_db)
):
    """Verify user email using verification token."""
    try:
        success = user_service.verify_user_email(db, verification_token)
        
        if success:
            return {"message": "Email verified successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to verify email"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        ) 