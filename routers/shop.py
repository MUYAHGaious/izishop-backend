from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from pydantic import ValidationError

from database.connection import get_db
from services.shop import (
    create_shop, 
    get_shop_by_id, 
    get_shop_by_owner_id,
    get_shops,
    get_active_shops,
    get_featured_shops,
    get_shop_products,
    get_shop_reviews,
    update_shop,
    delete_shop,
    verify_shop
)
from schemas.shop import ShopCreate, ShopUpdate, ShopResponse, ShopWithOwner
from schemas.user import UserResponse
from schemas.product import ProductResponse
from routers.auth import get_current_user
from models.user import UserRole

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/create", response_model=ShopResponse, status_code=status.HTTP_201_CREATED)
def create_user_shop(
    shop_data: ShopCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new shop for the current user (must be shop owner)
    """
    try:
        # Log shop creation attempt
        logger.info(f"Shop creation attempt by user: {current_user.email}")
        
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            logger.warning(f"Non-shop-owner attempted to create shop: {current_user.email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can create shops"
            )
        
        # Create the shop
        shop = create_shop(db=db, shop_data=shop_data, owner_id=current_user.id)
        
        logger.info(f"Shop created successfully: {shop.name} by {current_user.email}")
        
        return ShopResponse.from_orm(shop)
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ValidationError as e:
        # Handle Pydantic validation errors
        logger.error(f"Validation error during shop creation: {str(e)}")
        error_details = []
        for error in e.errors():
            field = '.'.join(str(x) for x in error['loc'])
            message = error['msg']
            error_details.append(f"{field}: {message}")
        
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Validation failed",
                "errors": error_details
            }
        )
    except ValueError as e:
        # Handle business logic errors
        logger.error(f"Business logic error during shop creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error during shop creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again."
        )

@router.get("/my-shop", response_model=ShopResponse)
def get_current_user_shop(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the current user's shop
    """
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can access shop data"
            )
        
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        return ShopResponse.from_orm(shop)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user shop: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shop"
        )

@router.get("/my-shops", response_model=List[ShopResponse])
def get_current_user_shops(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all shops owned by the current user (supports multiple shops per user)
    """
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can access shop data"
            )
        
        # Get all shops owned by user
        from services.shop import get_shops_by_owner_id
        shops = get_shops_by_owner_id(db=db, owner_id=current_user.id)
        
        return [ShopResponse.from_orm(shop) for shop in shops]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user shops: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shops"
        )

@router.get("/featured", response_model=List[ShopResponse])
def get_featured_shops_endpoint(
    limit: int = Query(default=10, le=50),
    db: Session = Depends(get_db)
):
    """
    Get featured shops (public endpoint)
    """
    try:
        shops = get_featured_shops(db=db, limit=limit)
        return [ShopResponse.from_orm(shop) for shop in shops]
    except Exception as e:
        logger.error(f"Error getting featured shops: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve featured shops"
        )

@router.get("/{shop_id}", response_model=ShopResponse)
def get_shop(shop_id: str, db: Session = Depends(get_db)):
    """
    Get a specific shop by ID (public endpoint)
    """
    try:
        shop = get_shop_by_id(db=db, shop_id=shop_id)
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        return ShopResponse.from_orm(shop)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop {shop_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shop"
        )

@router.get("/", response_model=List[ShopResponse])
def get_all_shops(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    Get all shops (public endpoint)
    """
    try:
        if active_only:
            shops = get_active_shops(db=db, skip=skip, limit=limit)
        else:
            shops = get_shops(db=db, skip=skip, limit=limit)
        
        return [ShopResponse.from_orm(shop) for shop in shops]
        
    except Exception as e:
        logger.error(f"Error getting shops: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shops"
        )

@router.put("/my-shop", response_model=ShopResponse)
def update_current_user_shop(
    shop_data: ShopUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update the current user's shop
    """
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can update shops"
            )
        
        # Get user's shop
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Update the shop
        updated_shop = update_shop(db=db, shop_id=shop.id, shop_data=shop_data)
        
        if not updated_shop:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update shop"
            )
        
        logger.info(f"Shop updated: {shop.id} by {current_user.email}")
        
        return ShopResponse.from_orm(updated_shop)
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Business logic error during shop update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating shop: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update shop"
        )

@router.delete("/my-shop")
def delete_current_user_shop(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete the current user's shop (soft delete)
    """
    try:
        # Verify user is a shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can delete shops"
            )
        
        # Get user's shop
        shop = get_shop_by_owner_id(db=db, owner_id=current_user.id)
        
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Delete the shop
        success = delete_shop(db=db, shop_id=shop.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete shop"
            )
        
        logger.info(f"Shop deleted: {shop.id} by {current_user.email}")
        
        return {"message": "Shop deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting shop: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete shop"
        )

# Admin endpoints
@router.post("/{shop_id}/verify")
def verify_shop_admin(
    shop_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Verify a shop (admin only)
    """
    try:
        # Verify user is admin
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can verify shops"
            )
        
        success = verify_shop(db=db, shop_id=shop_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        logger.info(f"Shop verified: {shop_id} by admin {current_user.email}")
        
        return {"message": "Shop verified successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying shop: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify shop"
        )

@router.get("/{shop_id}/products", response_model=List[ProductResponse])
def get_shop_products_endpoint(
    shop_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db)
):
    """
    Get products for a specific shop (public endpoint)
    """
    try:
        # Verify shop exists
        shop = get_shop_by_id(db=db, shop_id=shop_id)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Get products with pagination
        skip = (page - 1) * limit
        products = get_shop_products(db=db, shop_id=shop_id, skip=skip, limit=limit)
        
        return [ProductResponse.from_orm(product) for product in products]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting products for shop {shop_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shop products"
        )

@router.get("/{shop_id}/reviews")
def get_shop_reviews_endpoint(
    shop_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, le=100),
    db: Session = Depends(get_db)
):
    """
    Get reviews for a specific shop (public endpoint)
    """
    try:
        # Verify shop exists
        shop = get_shop_by_id(db=db, shop_id=shop_id)
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Get reviews with pagination
        skip = (page - 1) * limit
        reviews = get_shop_reviews(db=db, shop_id=shop_id, skip=skip, limit=limit)
        
        # For now, return empty list as we don't have review models yet
        # This will be implemented when review functionality is added
        return {"reviews": reviews, "total": len(reviews)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting reviews for shop {shop_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve shop reviews"
        )

@router.get("/check-name/{shop_name}")
def check_shop_name_availability(shop_name: str, db: Session = Depends(get_db)):
    """Check if shop name is available."""
    try:
        # URL decode the shop name
        from urllib.parse import unquote
        decoded_name = unquote(shop_name)
        
        # Clean and validate shop name
        clean_name = decoded_name.strip()
        if len(clean_name) < 2:
            return {"available": False, "message": "Shop name must be at least 2 characters"}
        
        if len(clean_name) > 100:
            return {"available": False, "message": "Shop name must not exceed 100 characters"}
        
        # Check if name exists
        from services.shop import get_shop_by_name
        existing_shop = get_shop_by_name(db, name=clean_name)
        available = existing_shop is None
        
        suggestions = []
        if not available:
            # Generate suggestions
            for i in range(1, 4):
                suggestion = f"{clean_name} ({i})"
                if not get_shop_by_name(db, name=suggestion):
                    suggestions.append(suggestion)
        
        return {
            "available": available,
            "message": "Shop name is available" if available else "Shop name is already taken",
            "suggestions": suggestions[:2] if suggestions else []
        }
        
    except Exception as e:
        logger.error(f"Error checking shop name availability: {str(e)}")
        return {"available": False, "message": "Unable to check shop name availability"}

@router.get("/check-phone/{phone}")
def check_shop_phone_availability(phone: str, db: Session = Depends(get_db)):
    """Check if shop phone number is available."""
    try:
        # URL decode the phone number
        from urllib.parse import unquote
        decoded_phone = unquote(phone)
        
        # Clean phone number (remove all non-digit characters for comparison)
        import re
        clean_phone = re.sub(r'\D', '', decoded_phone)
        
        # Validate phone number format (must be between 9 and 15 digits)
        if len(clean_phone) < 9 or len(clean_phone) > 15:
            return {"available": False, "message": "Phone number must contain 9 to 15 digits (letters and symbols are not allowed)"}
        
        # Check if phone exists in shops
        from services.shop import get_shop_by_phone
        existing_shop = get_shop_by_phone(db, phone=clean_phone)
        available = existing_shop is None
        
        return {
            "available": available,
            "message": "Phone number is available" if available else "Phone number is already used by another shop",
            "suggestions": []
        }
        
    except Exception as e:
        logger.error(f"Error checking shop phone availability: {str(e)}")
        return {"available": False, "message": "Unable to check phone availability"}

@router.get("/check-license/{license_number}")
def check_business_license_availability(license_number: str, db: Session = Depends(get_db)):
    """Check if business license number is available."""
    try:
        # URL decode the license number
        from urllib.parse import unquote
        decoded_license = unquote(license_number)
        
        # Clean and validate license number
        clean_license = decoded_license.strip()
        if len(clean_license) < 3:
            return {"available": False, "message": "Business license must be at least 3 characters"}
        
        if len(clean_license) > 50:
            return {"available": False, "message": "Business license must not exceed 50 characters"}
        
        # For now, we'll just validate format since there's no license field in database
        # This can be extended to check against a business registry API or database
        return {
            "available": True,
            "message": "Business license format is valid",
            "suggestions": []
        }
        
    except Exception as e:
        logger.error(f"Error checking business license availability: {str(e)}")
        return {"available": False, "message": "Unable to check business license"}