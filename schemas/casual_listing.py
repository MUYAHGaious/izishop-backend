"""
Pydantic schemas for casual listings
"""
from pydantic import BaseModel, validator
from typing import List, Optional
from decimal import Decimal
from datetime import datetime

class CasualListingBase(BaseModel):
    title: str
    description: str
    price: Decimal
    condition: str
    category: str
    location: str
    is_negotiable: bool = False
    images: Optional[List[str]] = []
    tags: Optional[List[str]] = []

    @validator('price')
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than 0')
        if v > 999999.99:
            raise ValueError('Price cannot exceed $999,999.99')
        return v

    @validator('title')
    def validate_title(cls, v):
        if len(v.strip()) < 3:
            raise ValueError('Title must be at least 3 characters long')
        if len(v) > 200:
            raise ValueError('Title cannot exceed 200 characters')
        return v.strip()

    @validator('description')
    def validate_description(cls, v):
        if len(v.strip()) < 10:
            raise ValueError('Description must be at least 10 characters long')
        if len(v) > 2000:
            raise ValueError('Description cannot exceed 2000 characters')
        return v.strip()

    @validator('condition')
    def validate_condition(cls, v):
        valid_conditions = [
            "New", "Like New", "Very Good", "Good", 
            "Fair", "Poor", "For Parts"
        ]
        if v not in valid_conditions:
            raise ValueError(f'Condition must be one of: {", ".join(valid_conditions)}')
        return v

    @validator('category')
    def validate_category(cls, v):
        valid_categories = [
            "Electronics", "Clothing & Accessories", "Home & Garden",
            "Books & Media", "Sports & Recreation", "Vehicles",
            "Furniture", "Toys & Games", "Health & Beauty",
            "Tools & Equipment", "Art & Crafts", "Musical Instruments",
            "Food & Beverages", "Other"
        ]
        if v not in valid_categories:
            raise ValueError(f'Category must be one of: {", ".join(valid_categories)}')
        return v

    @validator('images')
    def validate_images(cls, v):
        if v and len(v) > 10:
            raise ValueError('Maximum 10 images allowed')
        return v

    @validator('tags')
    def validate_tags(cls, v):
        if v and len(v) > 20:
            raise ValueError('Maximum 20 tags allowed')
        if v:
            for tag in v:
                if len(tag) > 30:
                    raise ValueError('Tags cannot exceed 30 characters each')
        return v

class CasualListingCreate(CasualListingBase):
    pass

class CasualListingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    condition: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    is_negotiable: Optional[bool] = None
    images: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @validator('price')
    def validate_price(cls, v):
        if v is not None:
            if v <= 0:
                raise ValueError('Price must be greater than 0')
            if v > 999999.99:
                raise ValueError('Price cannot exceed $999,999.99')
        return v

    @validator('title')
    def validate_title(cls, v):
        if v is not None:
            if len(v.strip()) < 3:
                raise ValueError('Title must be at least 3 characters long')
            if len(v) > 200:
                raise ValueError('Title cannot exceed 200 characters')
            return v.strip()
        return v

    @validator('description')
    def validate_description(cls, v):
        if v is not None:
            if len(v.strip()) < 10:
                raise ValueError('Description must be at least 10 characters long')
            if len(v) > 2000:
                raise ValueError('Description cannot exceed 2000 characters')
            return v.strip()
        return v

class CasualListingResponse(CasualListingBase):
    id: str
    seller_id: str
    is_active: bool
    views: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Seller info (populated from relationship)
    seller_name: Optional[str] = None
    seller_rating: Optional[float] = None

    class Config:
        from_attributes = True
        
    @classmethod
    def from_orm(cls, listing):
        # Basic listing data
        data = {
            'id': listing.id,
            'seller_id': listing.seller_id,
            'title': listing.title,
            'description': listing.description,
            'price': listing.price,
            'condition': listing.condition,
            'category': listing.category,
            'location': listing.location,
            'is_negotiable': listing.is_negotiable,
            'images': listing.images or [],
            'tags': listing.tags or [],
            'is_active': listing.is_active,
            'views': listing.views,
            'created_at': listing.created_at,
            'updated_at': listing.updated_at
        }
        
        # Add seller info if available
        if hasattr(listing, 'seller') and listing.seller:
            data['seller_name'] = f"{listing.seller.first_name} {listing.seller.last_name}"
            # TODO: Add seller rating from rating system
            data['seller_rating'] = 5.0  # Placeholder
            
        return cls(**data)

class CasualListingSearch(BaseModel):
    q: Optional[str] = None  # Search query
    category: Optional[str] = None
    condition: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    location: Optional[str] = None
    is_negotiable: Optional[bool] = None
    sort_by: Optional[str] = "created_at"  # created_at, price_asc, price_desc
    page: int = 1
    per_page: int = 20

    @validator('per_page')
    def validate_per_page(cls, v):
        if v < 1 or v > 100:
            raise ValueError('per_page must be between 1 and 100')
        return v

    @validator('sort_by')
    def validate_sort_by(cls, v):
        valid_sorts = ["created_at", "price_asc", "price_desc", "views"]
        if v not in valid_sorts:
            raise ValueError(f'sort_by must be one of: {", ".join(valid_sorts)}')
        return v