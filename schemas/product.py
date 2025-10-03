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

    # Enhanced product fields
    sku: Optional[str] = Field(None, max_length=50, description="Product SKU")
    brand: Optional[str] = Field(None, max_length=100, description="Product brand")
    condition: str = Field(default="new", description="Product condition (new, used, refurbished)")

    # Product specifications and physical attributes
    weight: Optional[float] = Field(None, gt=0, description="Product weight in kg")
    dimensions: Optional[dict] = Field(None, description="Product dimensions {length, width, height} in cm")
    specifications: Optional[dict] = Field(None, description="Technical specifications")
    materials: Optional[str] = Field(None, max_length=500, description="Product materials")
    manufacturing_location: Optional[str] = Field(None, max_length=100, description="Manufacturing location")

    # Warranty and return information
    warranty_months: Optional[int] = Field(None, ge=0, le=120, description="Warranty period in months")
    warranty_type: Optional[str] = Field(None, max_length=50, description="Warranty type (manufacturer, seller, extended)")
    warranty_details: Optional[str] = Field(None, max_length=1000, description="Detailed warranty information")
    return_policy: str = Field(default="30_days", description="Return policy (7_days, 15_days, 30_days, no_returns)")
    return_details: Optional[str] = Field(None, max_length=1000, description="Return policy details")

    # Advanced features
    tags: Optional[List[str]] = Field(default=[], description="Product tags for better search")
    seo_keywords: Optional[str] = Field(None, max_length=200, description="SEO keywords")
    featured: bool = Field(default=False, description="Featured product flag")

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

    @validator('condition')
    def validate_condition(cls, v):
        allowed_conditions = ['new', 'used', 'refurbished']
        if v not in allowed_conditions:
            raise ValueError(f'Condition must be one of: {allowed_conditions}')
        return v.lower()

class ProductCreate(ProductBase):
    pass

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: Optional[Decimal] = Field(None, gt=0)
    stock_quantity: Optional[int] = Field(None, ge=0)
    category: Optional[str] = Field(None, max_length=100)

    # Enhanced product fields
    sku: Optional[str] = Field(None, max_length=50)
    brand: Optional[str] = Field(None, max_length=100)
    condition: Optional[str] = Field(None, description="Product condition")

    # Product specifications
    weight: Optional[float] = Field(None, gt=0)
    dimensions: Optional[dict] = Field(None)
    specifications: Optional[dict] = Field(None)
    materials: Optional[str] = Field(None, max_length=500)
    manufacturing_location: Optional[str] = Field(None, max_length=100)

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

class ShopInfo(BaseModel):
    """Embedded shop information for products"""
    id: str
    owner_id: str  # The actual user ID who owns the shop - needed for messaging
    name: str
    owner_name: Optional[str] = None
    verified: bool = False
    rating: Optional[float] = None
    total_reviews: int = 0
    location: Optional[str] = None

class ProductResponse(BaseModel):
    id: str
    seller_id: str
    seller_name: Optional[str] = None  # Individual seller name (when no shop)
    name: str
    description: Optional[str]
    price: Decimal
    stock_quantity: int
    category: Optional[str]

    # Shop information - directly embedded
    shop: Optional[ShopInfo] = None

    # Enhanced product fields
    sku: Optional[str] = None
    brand: Optional[str] = None
    condition: str = "new"

    # Product specifications
    weight: Optional[float] = None
    dimensions: Optional[dict] = None
    specifications: Optional[dict] = None
    materials: Optional[str] = None
    manufacturing_location: Optional[str] = None

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