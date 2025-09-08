from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

class ProductBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Product name")
    description: Optional[str] = Field(None, max_length=2000, description="Product description")
    price: Decimal = Field(..., gt=0, description="Product price must be greater than 0")
    stock_quantity: int = Field(default=0, ge=0, description="Stock quantity must be non-negative")
    category: Optional[str] = Field(None, max_length=100, description="Product category")
    is_active: bool = Field(default=True, description="Whether the product is active")
    image_urls: Optional[List[str]] = Field(default=[], description="List of product image URLs")
    video_urls: Optional[List[str]] = Field(default=[], description="List of product video URLs")
    
    @validator('price')
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than 0')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Product name cannot be empty')
        return v.strip()
    
    @validator('description')
    def validate_description(cls, v):
        if v is not None:
            return v.strip()
        return v

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: Optional[Decimal] = Field(None, gt=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    category: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    image_urls: Optional[List[str]] = Field(None, description="List of product image URLs")
    video_urls: Optional[List[str]] = Field(None, description="List of product video URLs")
    
    @validator('price')
    def validate_price(cls, v):
        if v is not None and v <= 0:
            raise ValueError('Price must be greater than 0')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        if v is not None and (not v or not v.strip()):
            raise ValueError('Product name cannot be empty')
        return v.strip() if v else v

class ProductResponse(BaseModel):
    id: str
    seller_id: str
    name: str
    description: Optional[str]
    price: Decimal
    stock_quantity: int
    category: Optional[str]
    is_active: bool
    image_urls: Optional[List[str]] = []
    video_urls: Optional[List[str]] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ProductWithSeller(ProductResponse):
    seller: dict = Field(..., description="Seller information")
    
    class Config:
        from_attributes = True

class ProductListResponse(BaseModel):
    products: list[ProductResponse]
    total: int
    page: int
    per_page: int
    pages: int

class ProductReviewBase(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 to 5 stars")
    title: Optional[str] = Field(None, max_length=200, description="Review title")
    content: Optional[str] = Field(None, max_length=2000, description="Review content")

class ProductReviewCreate(ProductReviewBase):
    product_id: str = Field(..., description="ID of the product being reviewed")

class ProductReviewUpdate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating from 1 to 5 stars")
    title: Optional[str] = Field(None, max_length=200, description="Review title")
    content: Optional[str] = Field(None, max_length=2000, description="Review content")

class ProductReviewResponse(ProductReviewBase):
    id: str
    product_id: str
    user_id: str
    user_name: Optional[str] = None
    user_avatar: Optional[str] = None
    is_verified_purchase: bool
    is_active: bool
    helpful_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ProductReviewListResponse(BaseModel):
    reviews: List[ProductReviewResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

class ProductReviewStats(BaseModel):
    average_rating: float
    total_reviews: int
    rating_distribution: Dict[int, int]  # {1: count, 2: count, ...}