from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ReviewBase(BaseModel):
    rating: float
    title: Optional[str] = None
    comment: Optional[str] = None
    is_verified_purchase: bool = False

class ReviewCreate(ReviewBase):
    shop_id: str
    product_id: Optional[str] = None

class ReviewUpdate(BaseModel):
    rating: Optional[float] = None
    title: Optional[str] = None
    comment: Optional[str] = None

class ReviewResponse(ReviewBase):
    id: str
    shop_id: str
    user_id: str
    product_id: Optional[str] = None
    helpful_count: int
    created_at: datetime
    updated_at: datetime
    
    # User information
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None
    
    class Config:
        from_attributes = True
