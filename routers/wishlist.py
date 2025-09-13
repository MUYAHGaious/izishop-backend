"""
Wishlist Router
Handles wishlist-related API endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import logging

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from models.wishlist import Wishlist, WishlistPreference
from models.product import Product
from models.user import User
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/wishlist", tags=["Wishlist"])


# Pydantic schemas
class WishlistItemResponse(BaseModel):
    id: str
    user_id: str
    product_id: str
    added_at: datetime
    updated_at: Optional[datetime] = None
    priority: Optional[str] = None
    notes: Optional[str] = None
    product: Optional[dict] = None

    class Config:
        from_attributes = True


class WishlistPreferenceResponse(BaseModel):
    id: str
    user_id: str
    price_drop_notifications: bool
    stock_availability_notifications: bool
    weekly_summary_notifications: bool
    auto_remove_unavailable: bool
    max_wishlist_size: str
    wishlist_public: bool
    allow_wishlist_sharing: bool

    class Config:
        from_attributes = True


class AddToWishlistRequest(BaseModel):
    product_id: str
    priority: Optional[str] = "normal"
    notes: Optional[str] = None


class UpdateWishlistPreferencesRequest(BaseModel):
    price_drop_notifications: Optional[bool] = None
    stock_availability_notifications: Optional[bool] = None
    weekly_summary_notifications: Optional[bool] = None
    auto_remove_unavailable: Optional[bool] = None
    max_wishlist_size: Optional[str] = None
    wishlist_public: Optional[bool] = None
    allow_wishlist_sharing: Optional[bool] = None


@router.get("/", response_model=List[WishlistItemResponse])
async def get_wishlist_items(
    limit: int = 50,
    offset: int = 0,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's wishlist items"""
    try:
        wishlist_items = db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id
        ).offset(offset).limit(limit).all()

        # Convert to response format with product details
        result = []
        for item in wishlist_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            item_dict = {
                "id": item.id,
                "user_id": item.user_id,
                "product_id": item.product_id,
                "added_at": item.added_at,
                "updated_at": item.updated_at,
                "priority": item.priority,
                "notes": item.notes,
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "price": float(product.price),
                    "image_urls": product.image_urls,
                    "is_active": product.is_active,
                    "stock_quantity": product.stock_quantity,
                    "category": product.category
                } if product else None
            }
            result.append(item_dict)

        return result

    except Exception as e:
        logger.error(f"Error getting wishlist items: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get wishlist items"
        )


@router.post("/add", response_model=WishlistItemResponse)
async def add_to_wishlist(
    request: AddToWishlistRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add item to wishlist"""
    try:
        # Check if product exists
        product = db.query(Product).filter(Product.id == request.product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Check if already in wishlist
        existing = db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == request.product_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Product already in wishlist"
            )

        # Create wishlist item
        wishlist_item = Wishlist(
            user_id=current_user.id,
            product_id=request.product_id,
            added_at=datetime.now(timezone.utc),
            priority=request.priority,
            notes=request.notes
        )

        db.add(wishlist_item)
        db.commit()
        db.refresh(wishlist_item)

        # Return with product details
        return {
            "id": wishlist_item.id,
            "user_id": wishlist_item.user_id,
            "product_id": wishlist_item.product_id,
            "added_at": wishlist_item.added_at,
            "updated_at": wishlist_item.updated_at,
            "priority": wishlist_item.priority,
            "notes": wishlist_item.notes,
            "product": {
                "id": product.id,
                "name": product.name,
                "price": float(product.price),
                "image_urls": product.image_urls,
                "is_active": product.is_active,
                "stock_quantity": product.stock_quantity,
                "category": product.category
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to wishlist: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add to wishlist"
        )


@router.delete("/{product_id}")
async def remove_from_wishlist(
    product_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove item from wishlist"""
    try:
        wishlist_item = db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == product_id
        ).first()

        if not wishlist_item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found in wishlist"
            )

        db.delete(wishlist_item)
        db.commit()

        return {"message": "Item removed from wishlist"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from wishlist: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove from wishlist"
        )


@router.post("/toggle/{product_id}")
async def toggle_wishlist_item(
    product_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle item in/out of wishlist"""
    try:
        # Check if product exists
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Check if already in wishlist
        existing = db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == product_id
        ).first()

        if existing:
            # Remove from wishlist
            db.delete(existing)
            db.commit()
            return {
                "action": "removed",
                "message": "Item removed from wishlist",
                "in_wishlist": False
            }
        else:
            # Add to wishlist
            wishlist_item = Wishlist(
                user_id=current_user.id,
                product_id=product_id,
                added_at=datetime.now(timezone.utc)
            )
            db.add(wishlist_item)
            db.commit()
            return {
                "action": "added",
                "message": "Item added to wishlist",
                "in_wishlist": True
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling wishlist item: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to toggle wishlist item"
        )


@router.get("/count")
async def get_wishlist_count(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's wishlist count"""
    try:
        count = db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id
        ).count()

        return {"count": count}

    except Exception as e:
        logger.error(f"Error getting wishlist count: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get wishlist count"
        )


@router.delete("/clear")
async def clear_wishlist(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Clear all items from wishlist"""
    try:
        count = db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id
        ).count()

        db.query(Wishlist).filter(
            Wishlist.user_id == current_user.id
        ).delete()

        db.commit()

        return {
            "message": "Wishlist cleared",
            "items_removed": count
        }

    except Exception as e:
        logger.error(f"Error clearing wishlist: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear wishlist"
        )


@router.get("/preferences", response_model=WishlistPreferenceResponse)
async def get_wishlist_preferences(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's wishlist preferences"""
    try:
        preferences = db.query(WishlistPreference).filter(
            WishlistPreference.user_id == current_user.id
        ).first()

        if not preferences:
            # Create default preferences
            preferences = WishlistPreference(
                user_id=current_user.id
            )
            db.add(preferences)
            db.commit()
            db.refresh(preferences)

        return preferences

    except Exception as e:
        logger.error(f"Error getting wishlist preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get wishlist preferences"
        )


@router.put("/preferences", response_model=WishlistPreferenceResponse)
async def update_wishlist_preferences(
    request: UpdateWishlistPreferencesRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's wishlist preferences"""
    try:
        preferences = db.query(WishlistPreference).filter(
            WishlistPreference.user_id == current_user.id
        ).first()

        if not preferences:
            preferences = WishlistPreference(user_id=current_user.id)
            db.add(preferences)

        # Update fields if provided
        update_data = request.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(preferences, field, value)

        preferences.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(preferences)

        return preferences

    except Exception as e:
        logger.error(f"Error updating wishlist preferences: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update wishlist preferences"
        )