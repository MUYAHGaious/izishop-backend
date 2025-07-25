from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, validator, Field

# Rating Schemas
class RatingBase(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    review: Optional[str] = Field(None, max_length=2000, description="Optional review text")

class RatingCreate(RatingBase):
    pass

class RatingUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    review: Optional[str] = Field(None, max_length=2000)

class RatingResponse(RatingBase):
    id: str
    user_id: str
    shop_id: str
    is_verified_purchase: bool
    helpful_count: int
    not_helpful_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class RatingWithUser(RatingResponse):
    user_name: str
    user_first_name: str
    user_profile_image: Optional[str]

# Rating Helpfulness Schemas
class RatingHelpfulnessCreate(BaseModel):
    is_helpful: bool

class RatingHelpfulnessResponse(BaseModel):
    id: str
    rating_id: str
    user_id: str
    is_helpful: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Rating Flag Schemas
class RatingFlagCreate(BaseModel):
    reason: str = Field(..., description="Reason for flagging (spam, inappropriate, fake, etc.)")
    description: Optional[str] = Field(None, max_length=500)

class RatingFlagResponse(BaseModel):
    id: str
    rating_id: str
    user_id: str
    reason: str
    description: Optional[str]
    is_resolved: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Shop Rating Statistics
class ShopRatingStats(BaseModel):
    average_rating: float
    total_reviews: int
    rating_distribution: dict  # {1: count, 2: count, ...}

class ShopStatsResponse(BaseModel):
    shop_id: str
    average_rating: float
    total_reviews: int
    total_orders: int
    total_products: int
    total_sales: float
    response_rate: float
    response_time_hours: float
    updated_at: datetime

    class Config:
        from_attributes = True

# Paginated responses
class PaginatedRatings(BaseModel):
    ratings: List[RatingWithUser]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

# Admin moderation schemas
class AdminRatingAction(BaseModel):
    action: str = Field(..., description="approve, hide, delete, warn_user")
    admin_notes: Optional[str] = Field(None, max_length=500)

class AdminRatingResponse(RatingResponse):
    is_flagged: bool
    admin_notes: Optional[str]
    flags_count: int

# Review summary for shop
class ShopReviewSummary(BaseModel):
    shop_id: str
    shop_name: str
    average_rating: float
    total_reviews: int
    rating_distribution: dict
    recent_reviews: List[RatingWithUser]
    verified_purchase_percentage: float

# User rating history
class UserRatingHistory(BaseModel):
    user_id: str
    ratings_given: List[RatingResponse]
    total_ratings: int
    average_rating_given: float