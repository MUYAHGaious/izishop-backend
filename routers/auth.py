from fastapi import APIRouter, Depends, HTTPException, status, Request

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session

from datetime import timedelta, datetime, timezone

from typing import Optional, Dict, Any

import logging

from pydantic import ValidationError



from database.connection import get_db
from models.user import User, UserRole

from services.auth import (

    authenticate_user, 

    create_user, 

    create_access_token,
    
    create_refresh_token,

    verify_token,

    update_last_login,

    get_user_by_email

)

from schemas.user import UserLogin, UserRegister, Token, UserResponse


from core.config import settings

from pydantic import BaseModel

class RoleChangeRequest(BaseModel):
    new_role: str
    reason: Optional[str] = None



# Configure logging

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)



router = APIRouter()

security = HTTPBearer(auto_error=False)



# Admin Login Schema

class AdminLogin(BaseModel):

    email: str

    password: str

    admin_code: str



# Dependency to get current user

def get_current_user(

    credentials: HTTPAuthorizationCredentials = Depends(security),

    db: Session = Depends(get_db)

) -> Optional[UserResponse]:

    """Get the current authenticated user with comprehensive validation."""

    try:

        if not credentials or not credentials.credentials:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Authentication credentials required",

                headers={"WWW-Authenticate": "Bearer"},

            )
        
        

        token = credentials.credentials

        token_data = verify_token(token)

        
        
        if token_data is None:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Could not validate credentials",

                headers={"WWW-Authenticate": "Bearer"},

            )
        
        

        # RACE CONDITION FIX: Retry user lookup to handle database transaction timing
        user = get_user_by_email(db, email=token_data.email)

        if user is None:
            # Retry once after small delay for race condition handling
            import time
            time.sleep(0.1)  # 100ms delay
            user = get_user_by_email(db, email=token_data.email)

            if user is None:
                logger.warning(f"Token valid but user not found after retry: {token_data.email}")

                raise HTTPException(

                    status_code=status.HTTP_401_UNAUTHORIZED,

                    detail="User not found",

                    headers={"WWW-Authenticate": "Bearer"},

                )
        
        

        # Check if user is still active

        if not user.is_active:

            logger.warning(f"Token valid but user inactive: {token_data.email}")

            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail="Account is inactive",

                headers={"WWW-Authenticate": "Bearer"},

            )
        
        

        return UserResponse.model_validate(user)
        
        

    except HTTPException:

        # Re-raise HTTP exceptions

        raise

    except Exception as e:

        logger.error(f"Unexpected error getting current user: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_401_UNAUTHORIZED,

            detail="Could not validate credentials",

            headers={"WWW-Authenticate": "Bearer"},

        )



@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, request: Request, db: Session = Depends(get_db)):
    """Register a new user and return an access token."""
    try:
        logger.info(f"Registration attempt for email: {user_data.email}")

        # Explicitly check if passwords match
        if user_data.password != user_data.confirm_password:
            logger.error("Password mismatch")
            raise ValueError("Passwords do not match")

        logger.info("About to create user")
        logger.info(f"User data: email={user_data.email}, first_name={user_data.first_name}, last_name={user_data.last_name}, role={user_data.role}, phone={user_data.phone}")
        
        # Create the user with detailed logging
        logger.info("=== CALLING CREATE_USER FUNCTION ===")
        user = create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            phone=user_data.phone
        )
        logger.info(f"=== CREATE_USER SUCCESS: {user.id} ===")
        logger.info(f"User created successfully: {user.id}")

        logger.info("About to create tokens")
        # Create access token and refresh token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id)},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )
        logger.info("Tokens created")

        logger.info("About to create UserResponse")
        # Create UserResponse - try both methods for compatibility
        try:
            user_response = UserResponse.model_validate(user)
        except Exception as model_error:
            logger.error(f"model_validate failed: {model_error}, trying from_orm")
            user_response = UserResponse.model_validate(user)
        logger.info("UserResponse created")

        logger.info("About to create Token response")
        token_result = Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=user_response
        )
        logger.info("Token response created")

        logger.info(f"User registered successfully: {user.email}")
        return token_result
        
    except ValueError as e:
        logger.warning(f"Registration failed for {user_data.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"CRITICAL ERROR during registration for {user_data.email}: {str(e)}", exc_info=True)
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Registration error: {str(e)}",
        )



@router.post("/login", response_model=Token)

async def login(user_credentials: UserLogin, request: Request, db: Session = Depends(get_db)):

    """Login user and return access token with enhanced security."""

    try:

        # Log login attempt

        logger.info(f"Login attempt for email: {user_credentials.email}")

        
        
        # Validate credentials

        if not user_credentials.email or not user_credentials.password:

            raise HTTPException(

                status_code=status.HTTP_400_BAD_REQUEST,

                detail="Email and password are required"

            )
        
        

        # Authenticate user

        user = authenticate_user(db, user_credentials.email, user_credentials.password)

        if not user:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Incorrect email or password",

                headers={"WWW-Authenticate": "Bearer"},

            )
        
        

        # Check if user is active

        if not user.is_active:

            logger.warning(f"Login attempt with inactive account: {user_credentials.email}")

            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail="Account is inactive. Please contact support."

            )
        
        

        # Update last login

        update_last_login(db, user)

        
        
        # Create access token

        access_token_expires = timedelta(

            minutes=getattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', 30)

        )

        access_token = create_access_token(

            data={"sub": user.email, "user_id": str(user.id)},

            expires_delta=access_token_expires

        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )

        
        
        logger.info(f"User logged in successfully: {user.email}")

        
        
        return Token(

            access_token=access_token,
            
            refresh_token=refresh_token,

            token_type="bearer",

            user=UserResponse.model_validate(user)

        )
        
        

    except HTTPException:

        # Re-raise HTTP exceptions

        raise

    except ValidationError as e:

        # Handle Pydantic validation errors

        logger.error(f"Validation error during login: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

            detail="Invalid login data format"

        )

    except Exception as e:

        # Handle unexpected errors

        logger.error(f"Unexpected error during login: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="An unexpected error occurred. Please try again."

        )



@router.post("/admin-login", response_model=Token)

async def admin_login(admin_credentials: AdminLogin, request: Request, db: Session = Depends(get_db)):

    """Admin login with access code verification."""

    try:

        # Log admin login attempt

        logger.info(f"Admin login attempt for email: {admin_credentials.email}")

        
        
        # Validate credentials

        if not admin_credentials.email or not admin_credentials.password or not admin_credentials.admin_code:

            raise HTTPException(

                status_code=status.HTTP_400_BAD_REQUEST,

                detail="Email, password, and admin access code are required"

            )
        
        

        # Verify admin access code

        if admin_credentials.admin_code != settings.ADMIN_ACCESS_CODE:

            logger.warning(f"Invalid admin access code attempt for email: {admin_credentials.email}")

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Invalid admin access code",

                headers={"WWW-Authenticate": "Bearer"},

            )
        
        

        # Authenticate user

        user = authenticate_user(db, admin_credentials.email, admin_credentials.password)

        if not user:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Incorrect email or password",

                headers={"WWW-Authenticate": "Bearer"},

            )
        
        

        # Check if user is admin

        if user.role != UserRole.ADMIN:

            logger.warning(f"Non-admin user attempted admin login: {admin_credentials.email}")

            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail="This account is not authorized for admin access"

            )
        
        

        # Check if user is active

        if not user.is_active:

            logger.warning(f"Admin login attempt with inactive account: {admin_credentials.email}")

            raise HTTPException(

                status_code=status.HTTP_403_FORBIDDEN,

                detail="Account is inactive. Please contact support."

            )
        
        

        # Update last login

        update_last_login(db, user)

        
        
        # Create access token

        access_token_expires = timedelta(

            minutes=getattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', 30)

        )

        access_token = create_access_token(

            data={"sub": user.email, "user_id": str(user.id)},

            expires_delta=access_token_expires

        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )

        
        
        logger.info(f"Admin logged in successfully: {user.email}")

        
        
        return Token(

            access_token=access_token,
            
            refresh_token=refresh_token,

            token_type="bearer",

            user=UserResponse.model_validate(user)

        )
        
        

    except HTTPException:

        # Re-raise HTTP exceptions

        raise

    except ValidationError as e:

        # Handle Pydantic validation errors

        logger.error(f"Validation error during admin login: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

            detail="Invalid admin login data format"

        )

    except Exception as e:

        # Handle unexpected errors

        logger.error(f"Unexpected error during admin login: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="An unexpected error occurred. Please try again."

        )



@router.get("/me")
def get_current_user_info(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user information with subscription data."""
    try:
        logger.info(f"User info requested for: {current_user.email}")
        
        # Fetch user with subscription data from database
        user_with_subscription = db.query(User).filter(User.id == current_user.id).first()
        if not user_with_subscription:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Convert to dict and add subscription data
        user_data = {
            "id": user_with_subscription.id,
            "email": user_with_subscription.email,
            "first_name": user_with_subscription.first_name,
            "last_name": user_with_subscription.last_name,
            "phone": user_with_subscription.phone,
            "role": user_with_subscription.role,
            "is_active": user_with_subscription.is_active,
            "is_verified": user_with_subscription.is_verified,
            "profile_image_url": user_with_subscription.profile_image_url,
            "created_at": user_with_subscription.created_at,
            "last_login": user_with_subscription.last_login,
        }
        
        # Add subscription data if exists
        if user_with_subscription.subscription:
            user_data["subscription"] = {
                "id": user_with_subscription.subscription.id,
                "plan_type": user_with_subscription.subscription.plan_type,
                "status": user_with_subscription.subscription.status,
                "current_period_start": user_with_subscription.subscription.current_period_start,
                "current_period_end": user_with_subscription.subscription.current_period_end,
                "monthly_fee": float(user_with_subscription.subscription.monthly_fee),
                "trial_ends_at": user_with_subscription.subscription.trial_ends_at,
                "created_at": user_with_subscription.subscription.created_at,
                "updated_at": user_with_subscription.subscription.updated_at
            }
        
        # If user is SHOP_OWNER but has no subscription, create one (for existing users)
        if (user_with_subscription.role == 'SHOP_OWNER' and 
            not user_with_subscription.subscription):
            
            logger.info(f"User {user_with_subscription.id} is SHOP_OWNER but has no subscription. Creating one...")
            
            from models.subscription import Subscription
            from datetime import datetime, timedelta
            
            # Create subscription record
            subscription = Subscription(
                user_id=user_with_subscription.id,
                plan_type='shop_owner',
                status='active',
                current_period_start=datetime.utcnow(),
                current_period_end=datetime.utcnow() + timedelta(days=30),
                monthly_fee=29.99,
                trial_ends_at=datetime.utcnow() + timedelta(days=7),
                tranzak_request_id=f"migration_{user_with_subscription.id}_{int(datetime.utcnow().timestamp())}"
            )
            
            db.add(subscription)
            
            # Create subscription notification
            try:
                from models.notification import Notification, NotificationType, NotificationPriority
                
                subscription_notification = Notification(
                    user_id=user_with_subscription.id,
                    type=NotificationType.SYSTEM,
                    title="🎉 Shop Owner Subscription Activated!",
                    message=f"""Congratulations, {user_with_subscription.first_name}! Your Shop Owner subscription is now active.

✅ SUBSCRIPTION DETAILS:
• Plan: Shop Owner ($29.99/month)
• Status: Active
• Trial Period: 7 days free
• Next Billing: {subscription.current_period_end.strftime('%B %d, %Y')}

🏬 WHAT'S INCLUDED:
• Unlimited product listings
• Advanced analytics dashboard
• Customer management tools
• Marketing and promotion features
• Priority customer support

💡 TIP: Use your 7-day free trial to explore all features before your first billing cycle!

Need help? Contact our support team anytime!

IziShopin Team 🚀""",
                    related_id=str(subscription.id),
                    related_type="subscription_created",
                    priority=NotificationPriority.HIGH,
                    action_url="/shop-owner-dashboard",
                    action_label="Open Dashboard",
                    icon="CreditCard"
                )
                
                db.add(subscription_notification)
                logger.info(f"Subscription notification created for user {user_with_subscription.email}")
                
            except Exception as notif_error:
                logger.warning(f"Failed to create subscription notification: {str(notif_error)}")
            
            db.commit()
            
            # Refresh user data to include the new subscription
            user_with_subscription = db.query(User).filter(User.id == current_user.id).first()
            
            # Add subscription data if exists
            if user_with_subscription.subscription:
                user_data["subscription"] = {
                    "id": user_with_subscription.subscription.id,
                    "plan_type": user_with_subscription.subscription.plan_type,
                    "status": user_with_subscription.subscription.status,
                    "current_period_start": user_with_subscription.subscription.current_period_start,
                    "current_period_end": user_with_subscription.subscription.current_period_end,
                    "monthly_fee": float(user_with_subscription.subscription.monthly_fee),
                    "trial_ends_at": user_with_subscription.subscription.trial_ends_at,
                    "created_at": user_with_subscription.subscription.created_at,
                    "updated_at": user_with_subscription.subscription.updated_at
                }
        
        return user_data

    except Exception as e:

        logger.error(f"Error getting user info: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="Could not retrieve user information"

        )



@router.post("/logout")

async def logout(current_user: UserResponse = Depends(get_current_user)):

    """Logout user (client should discard token)."""

    try:

        logger.info(f"User logged out: {current_user.email}")

        return {"message": "Successfully logged out"}

    except Exception as e:

        logger.error(f"Error during logout: {str(e)}")

        # Return success anyway since logout is client-side

        return {"message": "Successfully logged out"}



@router.get("/check-email/{email}")

def check_email_availability(email: str, db: Session = Depends(get_db)):

    """Check if email is available for registration."""

    try:

        # URL decode the email

        from urllib.parse import unquote

        decoded_email = unquote(email)

        

        logger.info(f"Checking email availability for: {decoded_email}")

        

        # Validate email format

        import re

        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

        if not re.match(email_regex, decoded_email):

            logger.warning(f"Invalid email format: {decoded_email}")

            return {"available": False, "message": "Invalid email format"}

        

        existing_user = get_user_by_email(db, email=decoded_email)

        available = existing_user is None

        

        return {

            "available": available,

            "message": "Email is available" if available else "Email is already registered"

        }

        

    except Exception as e:

        logger.error(f"Error checking email availability: {str(e)}")

        return {"available": False, "message": "Unable to check email availability"}



@router.get("/check-phone/{phone}")

def check_phone_availability(phone: str, db: Session = Depends(get_db)):

    """Check if phone number is available for registration."""

    try:

        # URL decode the phone number

        from urllib.parse import unquote

        decoded_phone = unquote(phone)

        

        logger.info(f"Checking phone availability for: {decoded_phone}")

        

        # Clean phone number (remove all non-digit characters for comparison)

        import re

        clean_phone = re.sub(r'\D', '', decoded_phone)

        

        # Validate phone number format (must be between 9 and 15 digits)

        if len(clean_phone) < 9 or len(clean_phone) > 15:

            return {"available": False, "message": "Phone number must contain 9 to 15 digits (letters and symbols are not allowed)"}

        

        # Check if phone exists in database

        from services.auth import get_user_by_phone

        existing_user = get_user_by_phone(db, phone=clean_phone)

        available = existing_user is None

        

        return {

            "available": available,

            "message": "Phone number is available" if available else "Phone number is already registered"

        }

        

    except Exception as e:

        logger.error(f"Error checking phone availability: {str(e)}")

        return {"available": False, "message": "Unable to check phone availability"}



# Refresh Token Schema

class RefreshTokenRequest(BaseModel):

    refresh_token: str



@router.post("/refresh", response_model=Token)

async def refresh_access_token(request: RefreshTokenRequest, db: Session = Depends(get_db)):

    """Refresh access token using refresh token."""

    try:

        logger.info("Token refresh attempt")

        

        # For now, we'll implement a simple refresh mechanism

        # In production, you'd want to validate the refresh token properly

        refresh_token = request.refresh_token

        

        if not refresh_token:

            raise HTTPException(

                status_code=status.HTTP_400_BAD_REQUEST,

                detail="Refresh token is required"

            )

        

        # Verify refresh token

        try:

            token_data = verify_token(refresh_token)

            if not token_data:

                raise HTTPException(

                    status_code=status.HTTP_401_UNAUTHORIZED,

                    detail="Invalid refresh token"

                )

        except Exception:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="Invalid or expired refresh token"

            )

        

        # Get user from database

        user = get_user_by_email(db, email=token_data.email)

        if not user or not user.is_active:

            raise HTTPException(

                status_code=status.HTTP_401_UNAUTHORIZED,

                detail="User not found or inactive"

            )

        

        # Create new access token

        access_token_expires = timedelta(

            minutes=getattr(settings, 'ACCESS_TOKEN_EXPIRE_MINUTES', 30)

        )

        new_access_token = create_access_token(

            data={"sub": user.email, "user_id": str(user.id)},

            expires_delta=access_token_expires

        )

        

        logger.info(f"Token refreshed successfully for user: {user.email}")

        

        # Issue new refresh token for security (token rotation)
        new_refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )
        
        return Token(

            access_token=new_access_token,
            
            refresh_token=new_refresh_token,

            token_type="bearer",

            user=UserResponse.model_validate(user)

        )

        

    except HTTPException:

        raise

    except Exception as e:

        logger.error(f"Unexpected error during token refresh: {str(e)}")

        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="Could not refresh token"

        )



@router.get("/profile/days-active")

async def get_user_days_active(

    current_user: UserResponse = Depends(get_current_user),

    db: Session = Depends(get_db)

):

    """Get the number of days the user has been active."""

    try:

        from datetime import datetime

        

        # Calculate days since user creation

        if hasattr(current_user, 'created_at') and current_user.created_at:

            created_date = current_user.created_at

            if isinstance(created_date, str):

                created_date = datetime.fromisoformat(created_date.replace('Z', '+00:00'))

            

            days_active = (datetime.now() - created_date.replace(tzinfo=None)).days + 1

        else:

            # Fallback: try to get from database

            from models.user import User

            user = db.query(User).filter(User.id == current_user.id).first()

            if user and user.created_at:

                days_active = (datetime.now() - user.created_at).days + 1

            else:

                days_active = 1  # Default for new users

        

        return {"days_active": max(1, days_active)}

        

    except Exception as e:

        logger.error(f"Error getting user days active: {str(e)}")

        return {"days_active": 1}  # Default fallback


@router.patch("/upgrade-role")
async def upgrade_user_role(
    role_data: Dict[str, str],
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Upgrade user role (CUSTOMER -> SHOP_OWNER or DELIVERY_AGENT)"""
    try:
        from models.user import UserRole
        from models.shop import Shop
        
        new_role = role_data.get("role")
        if not new_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role is required"
            )
        
        # Validate role
        valid_roles = ["SHOP_OWNER", "DELIVERY_AGENT", "CASUAL_SELLER"]
        if new_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {valid_roles}"
            )
        
        # Check if user is already this role
        if current_user.role == new_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User is already a {new_role}"
            )
        
        # Update user role
        logger.info(f"Upgrading user {current_user.email} from {current_user.role} to {new_role}")
        
        from models.user import User
        db.query(User).filter(User.id == current_user.id).update({
            "role": new_role,
            "updated_at": datetime.now(timezone.utc)
        })
        
        # If upgrading to SHOP_OWNER, create a shop
        if new_role == "SHOP_OWNER":
            try:
                # Check if user already has a shop
                existing_shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
                if not existing_shop:
                    logger.info(f"Creating shop for upgraded SHOP_OWNER: {current_user.email}")
                    
                    # Generate a default shop name based on user's name
                    shop_name = f"{current_user.first_name} {current_user.last_name}'s Shop".strip()
                    if not shop_name or shop_name == "'s Shop":
                        shop_name = f"Shop by {current_user.email.split('@')[0]}"
                    
                    new_shop = Shop(
                        owner_id=current_user.id,
                        name=shop_name,
                        description=f"Welcome to {shop_name}! We're excited to serve you.",
                        address="",  # User can update later
                        phone=current_user.phone or "",
                        email=current_user.email,
                        is_active=True,
                        is_verified=False
                    )
                    
                    db.add(new_shop)
                    logger.info(f"Shop created successfully: {shop_name}")
            except Exception as shop_error:
                logger.error(f"Failed to create shop during role upgrade: {str(shop_error)}")
                # Don't fail role upgrade if shop creation fails
                pass
        
        db.commit()
        logger.info(f"User role upgraded successfully: {current_user.email} -> {new_role}")
        
        return {
            "message": f"Role upgraded to {new_role} successfully",
            "new_role": new_role,
            "requires_refresh": True  # Frontend should refresh user data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Role upgrade failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upgrade role"
        ) 

@router.post("/change-role")
def change_user_role(
    request: RoleChangeRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change user role with confirmation"""
    try:
        logger.info(f"Role change requested for user {current_user.email}: {current_user.role} -> {request.new_role}")
        
        # Validate new role
        valid_roles = ['CUSTOMER', 'DELIVERY_AGENT', 'CASUAL_SELLER', 'SHOP_OWNER']
        if request.new_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )
        
        # Check if user is already this role
        if current_user.role == request.new_role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You are already a {request.new_role}"
            )
        
        # Get user from database
        user = db.query(User).filter(User.id == current_user.id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update user role
        old_role = user.role
        user.role = request.new_role
        user.updated_at = datetime.utcnow()
        
        # If downgrading from SHOP_OWNER, cancel any active subscription
        if old_role == 'SHOP_OWNER' and request.new_role != 'SHOP_OWNER':
            if user.subscription:
                user.subscription.status = 'cancelled'
                user.subscription.updated_at = datetime.utcnow()
                logger.info(f"Subscription cancelled for user {user.email} due to role downgrade")
                
                # Create subscription cancellation notification
                try:
                    from models.notification import Notification, NotificationType, NotificationPriority
                    
                    cancellation_notification = Notification(
                        user_id=user.id,
                        type=NotificationType.SYSTEM,
                        title="Shop Owner Subscription Cancelled",
                        message=f"Your Shop Owner subscription has been cancelled due to role change to {request.new_role}.",
                        related_id=str(user.subscription.id),
                        related_type="subscription_cancelled",
                        priority=NotificationPriority.MEDIUM,
                        action_url="/settings",
                        action_label="View Settings",
                        icon="XCircle"
                    )
                    
                    db.add(cancellation_notification)
                    logger.info(f"Subscription cancellation notification created for user {user.email}")
                    
                except Exception as notif_error:
                    logger.warning(f"Failed to create subscription cancellation notification: {str(notif_error)}")
        
        # Create simple notification for role change
        try:
            from models.notification import Notification, NotificationType, NotificationPriority
            
            notification = Notification(
                user_id=user.id,
                type=NotificationType.SYSTEM,
                title=f"Role Updated - {request.new_role}",
                message=f"Your role has been changed to {request.new_role} successfully.",
                related_id=str(user.id),
                related_type="role_change",
                priority=NotificationPriority.HIGH,
                action_url="/settings",
                action_label="View Settings",
                icon="User"
            )
            
            db.add(notification)
            logger.info(f"Role change notification created for user {user.email}")
            
        except Exception as notif_error:
            logger.warning(f"Failed to create role change notification: {str(notif_error)}")
        
        db.commit()
        logger.info(f"User role changed successfully: {user.email} {old_role} -> {request.new_role}")
        
        return {
            "success": True,
            "message": f"Role changed from {old_role} to {request.new_role} successfully",
            "new_role": request.new_role,
            "old_role": old_role
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Role change failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change role"
        ) 
