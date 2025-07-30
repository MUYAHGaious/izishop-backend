from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re

# Base Shop Schema
class ShopBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    profile_photo: Optional[str] = Field(None, max_length=500)
    background_image: Optional[str] = Field(None, max_length=500)

# Shop Creation Schema
class ShopCreate(ShopBase):
    @validator('name')
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError('Shop name must be at least 2 characters long')
        if not re.match(r'^[a-zA-Z0-9\s\-\'\&\.\(\)\[\]\_\,\!\@\#\%\+]+$', v.strip()):
            raise ValueError('Shop name contains invalid characters')
        return v.strip().title()
    
    @validator('phone')
    def validate_phone(cls, v):
        if v is None:
            return v
        # Remove all non-digit characters
        clean_phone = re.sub(r'\D', '', v)
        if len(clean_phone) < 9 or len(clean_phone) > 15:
            raise ValueError('Phone number must contain 9 to 15 digits (letters and symbols are not allowed)')
        return clean_phone
    
    @validator('email')
    def validate_email(cls, v):
        if v is None:
            return v
        # Basic email validation
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower().strip()

# Shop Update Schema
class ShopUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=100)
    profile_photo: Optional[str] = Field(None, max_length=500)
    background_image: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None

# Shop Response Schema
class ShopResponse(BaseModel):
    id: str
    owner_id: str
    name: str
    description: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    profile_photo: Optional[str]
    background_image: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

# Shop with Owner Schema
class ShopWithOwner(ShopResponse):
    owner: dict  # Will contain basic owner information
    
    class Config:
        from_attributes = True