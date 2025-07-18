from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging
from pydantic import ValidationError

from database.connection import get_db
from services.shop import (
    create_shop, 
    get_shop_by_id, 
    get_shop_by_owner_id,
    get_shops,
    get_active_shops,
    update_shop,
    delete_shop,
    verify_shop
)
from schemas.shop import ShopCreate, ShopUpdate, ShopResponse, ShopWithOwner
from schemas.user import UserResponse
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