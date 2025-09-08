from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

# Lightweight product schema WITHOUT base64 image data to prevent memory issues
class ProductLiteResponse(BaseModel):
    """
    Memory-efficient product response schema that uses image URLs instead of base64 data
    This prevents browser "Out of Memory" errors when loading product lists
    """
    id: str
    seller_id: str
    name: str
    description: Optional[str]
    price: Decimal
    stock_quantity: int
    category: Optional[str]
    is_active: bool
    # Use small image URLs instead of full base64 data
    image_url: Optional[str] = None  # Single primary image URL
    image_count: int = 0  # Number of images available
    has_video: bool = False  # Whether product has video
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ProductCatalogResponse(BaseModel):
    """Response format specifically optimized for product catalog listings"""
    products: List[ProductLiteResponse]
    total_count: int
    page: int
    per_page: int
    has_more: bool