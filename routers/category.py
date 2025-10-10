from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from database.connection import get_db
from core.response import success_response, empty_data_response, error_response
from core.exceptions import ResourceNotFoundError, BusinessLogicError
from sqlalchemy import func
from models.category import Category
from models.product import Product
from schemas.category import CategoryResponse, CategoryWithCount, CategoryCreate, CategoryUpdate
from schemas.user import UserResponse
from routers.auth import get_current_user
from models.user import UserRole

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[CategoryWithCount])
def get_categories(
    active_only: bool = Query(True, description="Only return active categories"),
    db: Session = Depends(get_db)
):
    """Get all categories with product counts"""
    try:
        query = db.query(Category)
        
        if active_only:
            query = query.filter(Category.is_active == True)
        
        categories = query.all()
        
        # Get product counts for each category
        category_data = []
        for category in categories:
            product_count = db.query(Product).filter(
                Product.category == category.name,
                Product.is_active == True
            ).count()
            
            category_dict = {
                "id": category.id,
                "name": category.name,
                "description": category.description,
                "parent_category_id": category.parent_category_id,
                "category_level": category.category_level or 0,
                "icon": category.icon,
                "is_active": category.is_active,
                "created_at": category.created_at,
                "updated_at": category.updated_at,
                "product_count": product_count
            }
            category_data.append(CategoryWithCount(**category_dict))
        
        return category_data
        
    except Exception as e:
        logger.error(f"Error getting categories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve categories"
        )

@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: str, db: Session = Depends(get_db)):
    """Get a specific category by ID"""
    try:
        category = db.query(Category).filter(Category.id == category_id).first()
        
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        return CategoryResponse.from_orm(category)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting category {category_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve category"
        )

@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    category_data: CategoryCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new category (admin only)"""
    try:
        # Check if user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can create categories"
            )
        
        # Check if category name already exists
        existing_category = db.query(Category).filter(Category.name == category_data.name).first()
        if existing_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name already exists"
            )
        
        # Create new category
        category = Category(
            name=category_data.name,
            description=category_data.description,
            is_active=category_data.is_active
        )
        
        db.add(category)
        db.commit()
        db.refresh(category)
        
        logger.info(f"Category created: {category.name} by {current_user.email}")
        
        return CategoryResponse.from_orm(category)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating category: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create category"
        )

@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: str,
    category_data: CategoryUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a category (admin only)"""
    try:
        # Check if user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can update categories"
            )
        
        # Get category
        category = db.query(Category).filter(Category.id == category_id).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        # Check if new name conflicts with existing category
        if category_data.name and category_data.name != category.name:
            existing_category = db.query(Category).filter(
                Category.name == category_data.name,
                Category.id != category_id
            ).first()
            if existing_category:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Category name already exists"
                )
        
        # Update category
        update_data = category_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(category, field, value)
        
        db.commit()
        db.refresh(category)
        
        logger.info(f"Category updated: {category.name} by {current_user.email}")
        
        return CategoryResponse.from_orm(category)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating category: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update category"
        )

@router.delete("/{category_id}")
def delete_category(
    category_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a category (admin only)"""
    try:
        # Check if user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can delete categories"
            )
        
        # Get category
        category = db.query(Category).filter(Category.id == category_id).first()
        if not category:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found"
            )
        
        # Check if category has products
        product_count = db.query(Product).filter(Product.category == category.name).count()
        if product_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete category with {product_count} products. Please reassign or delete products first."
            )
        
        # Delete category
        db.delete(category)
        db.commit()
        
        logger.info(f"Category deleted: {category.name} by {current_user.email}")
        
        return {"message": "Category deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting category: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete category"
        )
