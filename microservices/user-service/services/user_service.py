from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status, Depends
from models.user import User, UserRole
from schemas.user import UserResponse, UserProfileUpdate, PasswordChange
from services.auth_service import AuthService
from database.session import get_db
import logging

logger = logging.getLogger(__name__)

class UserService:
    """User management service for profile updates and user operations."""
    
    def __init__(self):
        self.auth_service = AuthService()
    
    def get_user_by_id(self, db: Session, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        try:
            return db.query(User).filter(User.id == user_id).first()
        except Exception as e:
            logger.error(f"Error getting user by ID: {str(e)}")
            return None
    
    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """Get a user by email address."""
        try:
            email = email.lower().strip()
            return db.query(User).filter(User.email == email).first()
        except Exception as e:
            logger.error(f"Error getting user by email: {str(e)}")
            return None
    
    def get_users_by_role(self, db: Session, role: UserRole, skip: int = 0, limit: int = 100) -> List[User]:
        """Get users by role with pagination."""
        try:
            return db.query(User).filter(User.role == role).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Error getting users by role: {str(e)}")
            return []
    
    def get_all_users(self, db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users with pagination."""
        try:
            return db.query(User).offset(skip).limit(limit).all()
        except Exception as e:
            logger.error(f"Error getting all users: {str(e)}")
            return []
    
    def update_user_profile(
        self, 
        db: Session, 
        user_id: str, 
        profile_update: UserProfileUpdate
    ) -> UserResponse:
        """Update user profile information."""
        try:
            user = self.get_user_by_id(db, user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Update fields if provided
            if profile_update.first_name is not None:
                user.first_name = profile_update.first_name.strip().title()
            
            if profile_update.last_name is not None:
                user.last_name = profile_update.last_name.strip().title()
            
            if profile_update.phone is not None:
                # Clean phone number
                clean_phone = ''.join(filter(str.isdigit, profile_update.phone))
                if len(clean_phone) < 9 or len(clean_phone) > 15:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Phone number must contain 9 to 15 digits"
                    )
                
                # Check if phone is already taken by another user
                existing_user = db.query(User).filter(
                    User.phone == clean_phone,
                    User.id != user_id
                ).first()
                if existing_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Phone number already in use by another user"
                    )
                
                user.phone = clean_phone
            
            if profile_update.profile_image_url is not None:
                user.profile_image_url = profile_update.profile_image_url
            
            # Update timestamp
            user.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(user)
            
            logger.info(f"Profile updated for user: {user.email}")
            return UserResponse.from_orm(user)
            
        except HTTPException:
            raise
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error updating profile: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile update failed due to data constraints"
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating user profile: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during profile update"
            )
    
    def change_password(
        self, 
        db: Session, 
        user_id: str, 
        password_change: PasswordChange
    ) -> bool:
        """Change user password with current password verification."""
        try:
            user = self.get_user_by_id(db, user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            # Verify current password
            if not self.auth_service.verify_password(password_change.current_password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect"
                )
            
            # Hash new password
            new_password_hash = self.auth_service.get_password_hash(password_change.new_password)
            
            # Update password
            user.password_hash = new_password_hash
            user.updated_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"Password changed for user: {user.email}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error changing password: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during password change"
            )
    
    def deactivate_user(self, db: Session, user_id: str) -> bool:
        """Deactivate a user account."""
        try:
            user = self.get_user_by_id(db, user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            user.is_active = False
            user.updated_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"User deactivated: {user.email}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error deactivating user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during user deactivation"
            )
    
    def activate_user(self, db: Session, user_id: str) -> bool:
        """Activate a user account."""
        try:
            user = self.get_user_by_id(db, user_id)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User not found"
                )
            
            user.is_active = True
            user.updated_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"User activated: {user.email}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error activating user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during user activation"
            )
    
    def verify_user_email(self, db: Session, verification_token: str) -> bool:
        """Verify user email using verification token."""
        try:
            user = db.query(User).filter(User.verification_token == verification_token).first()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid verification token"
                )
            
            user.is_verified = True
            user.verification_token = None
            user.updated_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"Email verified for user: {user.email}")
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error verifying email: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during email verification"
            )
    
    def search_users(
        self, 
        db: Session, 
        query: str, 
        role: Optional[UserRole] = None,
        skip: int = 0, 
        limit: int = 100
    ) -> List[User]:
        """Search users by name or email with optional role filter."""
        try:
            search_query = db.query(User)
            
            # Apply role filter if specified
            if role:
                search_query = search_query.filter(User.role == role)
            
            # Apply search query
            search_term = f"%{query.lower()}%"
            search_query = search_query.filter(
                (User.first_name.ilike(search_term)) |
                (User.last_name.ilike(search_term)) |
                (User.email.ilike(search_term))
            )
            
            return search_query.offset(skip).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Error searching users: {str(e)}")
            return []
    
    def get_user_statistics(self, db: Session) -> dict:
        """Get user statistics for analytics."""
        try:
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.is_active == True).count()
            verified_users = db.query(User).filter(User.is_verified == True).count()
            
            # Count by role
            role_counts = {}
            for role in UserRole:
                count = db.query(User).filter(User.role == role).count()
                role_counts[role.value] = count
            
            return {
                "total_users": total_users,
                "active_users": active_users,
                "verified_users": verified_users,
                "role_distribution": role_counts
            }
            
        except Exception as e:
            logger.error(f"Error getting user statistics: {str(e)}")
            return {} 