from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    description: Optional[str] = Field(None, max_length=500, description="Category description")

    # Hierarchical category support
    parent_category_id: Optional[str] = Field(None, description="Parent category ID")
    category_level: int = Field(default=0, ge=0, le=5, description="Category hierarchy level")
    sort_order: int = Field(default=0, description="Sort order within parent category")

    # Category-specific fields
    required_fields: Optional[List[str]] = Field(default=[], description="Required fields for products in this category")
    specifications_template: Optional[Dict[str, Any]] = Field(default={}, description="Default specifications template")
    icon: Optional[str] = Field(None, max_length=100, description="Category icon")

    is_active: bool = Field(default=True, description="Whether the category is active")

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None

class CategoryResponse(CategoryBase):
    id: str
    category_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CategoryWithCount(CategoryResponse):
    product_count: int = Field(..., description="Number of products in this category")

class CategoryTree(CategoryResponse):
    children: List["CategoryTree"] = Field(default=[], description="Child categories")

    class Config:
        from_attributes = True

# Enable forward reference resolution
CategoryTree.model_rebuild()
