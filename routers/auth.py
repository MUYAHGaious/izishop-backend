from fastapi import APIRouter, Depends, HTTPException, status, Request

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session

from datetime import timedelta

from typing import Optional, Dict, Any

import logging

from pydantic import ValidationError



from database.connection import get_db

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

from models.user import UserRole

from pydantic import BaseModel



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
        
        

        return UserResponse.from_orm(user)
        
        

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
async def register(user_data: UserRegister, request: Request, db: Session = Depends(get_db)):
    """Register a new user and return an access token."""
    try:
        logger.info(f"Registration attempt for email: {user_data.email}")

        # Create the user
        user = create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            role=user_data.role,
            phone=user_data.phone
        )

        # Create access token and refresh token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email, "user_id": str(user.id)},
            expires_delta=access_token_expires
        )
        
        refresh_token = create_refresh_token(
            data={"sub": user.email, "user_id": str(user.id)}
        )

        logger.info(f"User registered successfully: {user.email}")

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=UserResponse.from_orm(user)
        )
    except ValueError as e:
        logger.warning(f"Registration failed for {user_data.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during registration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration.",
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

            user=UserResponse.from_orm(user)

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

            user=UserResponse.from_orm(user)

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



@router.get("/me", response_model=UserResponse)

def get_current_user_info(current_user: UserResponse = Depends(get_current_user)):

    """Get current user information."""

    try:

        logger.info(f"User info requested for: {current_user.email}")

        return current_user

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

            user=UserResponse.from_orm(user)

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
