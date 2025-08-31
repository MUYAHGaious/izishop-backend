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

class AuthService:
    """Authentication service for user management and JWT token handling."""
    
    def __init__(self):
        self.security = HTTPBearer()
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)
    
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
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
                "iss": "izishop-user-service",
                "type": "access"
            })
            
            # Encode token
            encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
            logger.info(f"Access token created for user: {data.get('sub')}")
            
            return encoded_jwt
            
        except Exception as e:
            logger.error(f"Error creating access token: {str(e)}")
            raise
    
    def verify_token(self, token: str) -> Optional[TokenData]:
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
    
    def authenticate_user(self, db: Session, email: str, password: str) -> Optional[User]:
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
                logger.warning(f"Authentication attempt for inactive user: {email}")
                return None
            
            # Verify password
            if not self.verify_password(password, user.password_hash):
                logger.warning(f"Failed password verification for user: {email}")
                return None
            
            logger.info(f"Successful authentication for user: {email}")
            return user
            
        except Exception as e:
            logger.error(f"Error during user authentication: {str(e)}")
            return None
    
    def get_user_by_email(self, db: Session, email: str) -> Optional[User]:
        """Get a user by email address."""
        try:
            email = email.lower().strip()
            return db.query(User).filter(User.email == email).first()
        except Exception as e:
            logger.error(f"Error getting user by email: {str(e)}")
            return None
    
    def get_user_by_phone(self, db: Session, phone: str) -> Optional[User]:
        """Get a user by phone number."""
        try:
            # Clean phone number
            clean_phone = ''.join(filter(str.isdigit, phone))
            return db.query(User).filter(User.phone == clean_phone).first()
        except Exception as e:
            logger.error(f"Error getting user by phone: {str(e)}")
            return None
    
    def create_user(self, db: Session, email: str, password: str, first_name: str, 
                    last_name: str, role: UserRole, phone: Optional[str] = None) -> User:
        """Create a new user with enhanced validation and security."""
        try:
            # Normalize email
            email = email.lower().strip()
            
            # Check if user already exists
            existing_user = self.get_user_by_email(db, email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User with this email already exists"
                )
            
            # Check phone uniqueness if provided
            if phone:
                clean_phone = ''.join(filter(str.isdigit, phone))
                existing_phone_user = self.get_user_by_phone(db, clean_phone)
                if existing_phone_user:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="User with this phone number already exists"
                    )
                phone = clean_phone
            
            # Hash password
            password_hash = self.get_password_hash(password)
            
            # Create user
            user = User(
                email=email,
                password_hash=password_hash,
                first_name=first_name.strip().title(),
                last_name=last_name.strip().title(),
                role=role,
                phone=phone,
                verification_token=str(uuid.uuid4())
            )
            
            db.add(user)
            db.commit()
            db.refresh(user)
            
            logger.info(f"New user created: {email} with role {role}")
            return user
            
        except HTTPException:
            raise
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error creating user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User creation failed due to data constraints"
            )
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error during user creation"
            )
    
    def update_last_login(self, db: Session, user: User):
        """Update the user's last login timestamp."""
        try:
            user.last_login = datetime.utcnow()
            db.commit()
            logger.info(f"Updated last login for user: {user.email}")
        except Exception as e:
            logger.error(f"Error updating last login: {str(e)}")
            db.rollback()
    
    def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
        db: Session = Depends(get_db)
    ) -> UserResponse:
        """Get the current authenticated user from JWT token."""
        try:
            token = credentials.credentials
            token_data = self.verify_token(token)
            
            if token_data is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            user = self.get_user_by_email(db, email=token_data.email)
            if user is None:
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
            
            return UserResponse.from_orm(user)
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting current user: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error"
            )
    
    def get_admin_user(self, current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
        """Verify that the current user is an admin."""
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    
    def get_shop_owner_user(self, current_user: UserResponse = Depends(get_current_user)) -> UserResponse:
        """Verify that the current user is a shop owner."""
        if current_user.role not in [UserRole.SHOP_OWNER, UserRole.ADMIN]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Shop owner access required"
            )
        return current_user 