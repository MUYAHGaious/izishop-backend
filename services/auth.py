from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models.user import User, UserRole
from schemas.user import TokenData, UserResponse
from core.config import settings
from database.session import get_db
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with enhanced security."""
    try:
        to_encode = data.copy()
        
        # Set expiration time
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        # Add standard claims
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "iss": "izishop",
            "type": "access"
        })
        
        # Encode token
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"Access token created for user: {data.get('sub')}")
        
        return encoded_jwt
        
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise

def verify_token(token: str) -> Optional[TokenData]:
    """Verify and decode a JWT token with comprehensive error handling."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("user_id")
        
        if email is None or user_id is None:
            logger.warning("Token missing required claims")
            return None
            
        # Check if token is expired
        exp = payload.get("exp")
        if exp is None or datetime.utcnow().timestamp() > exp:
            logger.warning("Token is expired")
            return None
            
        return TokenData(email=email, user_id=user_id)
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error verifying token: {str(e)}")
        return None

def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    """Authenticate a user with email and password with enhanced security."""
    try:
        # Normalize email
        email = email.lower().strip()
        
        # Get user by email
        user = db.query(User).filter(User.email == email).first()
        if not user:
            logger.warning(f"Authentication attempt with non-existent email: {email}")
            return None
        
        # Check if user is active
        if not user.is_active:
            logger.warning(f"Authentication attempt with inactive user: {email}")
            return None
        
        # Verify password
        if not verify_password(password, user.password_hash):
            logger.warning(f"Authentication attempt with invalid password for user: {email}")
            return None
        
        logger.info(f"Successful authentication for user: {email}")
        return user
        
    except Exception as e:
        logger.error(f"Error during authentication for {email}: {str(e)}")
        return None

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get a user by email with proper error handling."""
    try:
        email = email.lower().strip()
        return db.query(User).filter(User.email == email).first()
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {str(e)}")
        return None

def get_user_by_phone(db: Session, phone: str) -> Optional[User]:
    """Get a user by phone number with proper error handling."""
    try:
        # Clean phone number (remove all non-digit characters)
        import re
        clean_phone = re.sub(r'\D', '', phone)
        return db.query(User).filter(User.phone == clean_phone).first()
    except Exception as e:
        logger.error(f"Error getting user by phone {phone}: {str(e)}")
        return None

def create_user(db: Session, email: str, password: str, first_name: str, last_name: str, 
                role: UserRole, phone: Optional[str] = None) -> User:
    """Create a new user with comprehensive validation and error handling."""
    try:
        # Check if user already exists
        existing_user = get_user_by_email(db, email)
        if existing_user:
            logger.warning(f"Attempt to create user with existing email: {email}")
            raise ValueError("User with this email already exists")
        
        # Check if phone number is already in use (if provided)
        if phone:
            existing_phone = db.query(User).filter(User.phone == phone).first()
            if existing_phone:
                logger.warning(f"Attempt to create user with existing phone: {phone}")
                raise ValueError("User with this phone number already exists")
        
        # Hash the password
        hashed_password = get_password_hash(password)
        
        # Create user object
        db_user = User(
            id=str(uuid.uuid4()),
            email=email.lower().strip(),
            password_hash=hashed_password,
            first_name=first_name,
            last_name=last_name,
            role=role,
            phone=phone,
            is_active=True,
            is_verified=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        logger.info(f"User created successfully: {email} with role {role}")
        return db_user
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error creating user {email}: {str(e)}")
        if "email" in str(e).lower():
            raise ValueError("User with this email already exists")
        elif "phone" in str(e).lower():
            raise ValueError("User with this phone number already exists")
        else:
            raise ValueError("Database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating user {email}: {str(e)}")
        raise

def update_last_login(db: Session, user: User):
    """Update user's last login timestamp with error handling."""
    try:
        user.last_login = datetime.utcnow()
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        logger.info(f"Updated last login for user: {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating last login for user {user.email}: {str(e)}")

# FastAPI Dependencies
security = HTTPBearer()

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> UserResponse:
    """Get current authenticated user."""
    try:
        # Extract token from credentials
        token = credentials.credentials
        
        # Verify token
        token_data = verify_token(token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database
        user = db.query(User).filter(User.id == token_data.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive user"
            )
        
        # Convert to UserResponse
        return UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=user.role,
            is_active=user.is_active,
            is_verified=user.is_verified,
            phone=user.phone,
            profile_image_url=user.profile_image_url,
            created_at=user.created_at,
            last_login=user.last_login
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting current user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_admin_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Get current user and verify admin privileges."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user

def get_shop_owner_user(current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Get current user and verify shop owner privileges."""
    if current_user.role not in [UserRole.SHOP_OWNER, UserRole.ADMIN]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Shop owner role required."
        )
    return current_user 