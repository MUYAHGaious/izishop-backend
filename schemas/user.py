from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional, Union
from datetime import datetime
from models.user import UserRole
import re

# Base User Schema
class UserBase(BaseModel):
    email: EmailStr
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    phone: Optional[str] = Field(None, max_length=20)
    role: Union[UserRole, str]

# User Registration Schema
class UserRegister(UserBase):
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    
    @validator('first_name')
    def validate_first_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('First name must be at least 2 characters long')
        if not re.match(r'^[a-zA-Z\s\-\']+$', v.strip()):
            raise ValueError('First name contains invalid characters')
        return v.strip().title()
    
    @validator('last_name')
    def validate_last_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Last name must be at least 2 characters long')
        if not re.match(r'^[a-zA-Z\s\-\']+$', v.strip()):
            raise ValueError('Last name contains invalid characters')
        return v.strip().title()
    
    @validator('phone')
    def validate_phone(cls, v):
        if v is None:
            return v
        # Remove all non-digit characters
        clean_phone = re.sub(r'\D', '', v)
        if len(clean_phone) < 9 or len(clean_phone) > 15:
            raise ValueError('Phone number must be between 9 and 15 digits')
        return clean_phone
    
    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if len(v) > 128:
            raise ValueError('Password must not exceed 128 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @validator('confirm_password')
    def validate_confirm_password(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v
    
    @validator('role')
    def validate_role(cls, v):
        if isinstance(v, str):
            # Handle string input and convert to enum
            try:
                return UserRole(v.upper())
            except ValueError:
                valid_roles = [role.value for role in UserRole]
                raise ValueError(f'Invalid role. Must be one of: {valid_roles}')
        return v

# User Login Schema
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# User Response Schema
class UserResponse(BaseModel):
    id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str]
    role: UserRole
    is_active: bool
    is_verified: bool
    profile_image_url: Optional[str]
    created_at: datetime
    last_login: Optional[datetime]
    
    class Config:
        from_attributes = True

# Token Schema
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

# Token Data Schema
class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[str] = None 