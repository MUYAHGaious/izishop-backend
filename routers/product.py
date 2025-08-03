from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from database.connection import get_db
from core.response import success_response, empty_data_response, error_response
from core.exceptions import ResourceNotFoundError, BusinessLogicError
from sqlalchemy import func
from services.product import (
    create_product,
    get_product_by_id,
    get_products_by_seller,
    get_all_products,
    search_products,
    update_product,
    delete_product,
    get_seller_product_stats,
    update_product_stock
)
from schemas.product import ProductCreate, ProductUpdate, ProductResponse, ProductListResponse
from schemas.user import UserResponse
from routers.auth import get_current_user
from models.user import UserRole

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_user_product(
    product_data: ProductCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new product (anyone can post, auto-assigns to shop if user is shop owner)"""
    try:
        # Create the product - anyone can create products now
        product = create_product(db=db, product_data=product_data, seller_id=current_user.id)
        
        # Log creation with appropriate context
        if current_user.role == UserRole.SHOP_OWNER:
            logger.info(f"Product created by shop owner: {product.name} by {current_user.email}")
        else:
            logger.info(f"Product created by individual seller: {product.name} by {current_user.email}")
        
        return ProductResponse.from_orm(product)
        
    except ValueError as e:
        logger.error(f"Business logic error during product creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during product creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again."
        )

@router.get("/my-products", response_model=List[ProductResponse])
def get_my_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    active_only: bool = Query(False),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's products"""
    try:
        products = get_products_by_seller(
            db=db, 
            seller_id=current_user.id, 
            skip=skip, 
            limit=limit, 
            active_only=active_only
        )
        
        return [ProductResponse.from_orm(product) for product in products]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products"
        )

@router.get("/my-stats", response_model=dict)
def get_my_product_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product statistics for current user"""
    try:
        stats = get_seller_product_stats(db=db, seller_id=current_user.id)
        
        return stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product statistics"
        )

@router.get("/", response_model=List[ProductResponse])
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get all products (public endpoint for product catalog)"""
    try:
        if search:
            products = search_products(db=db, search_term=search, skip=skip, limit=limit)
        else:
            products = get_all_products(db=db, skip=skip, limit=limit, active_only=active_only)
        
        return [ProductResponse.from_orm(product) for product in products]
        
    except Exception as e:
        logger.error(f"Error getting products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products"
        )

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    """Get a specific product by ID (public endpoint)"""
    try:
        product = get_product_by_id(db=db, product_id=product_id)
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        return ProductResponse.from_orm(product)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product {product_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product"
        )

@router.put("/{product_id}", response_model=ProductResponse)
def update_user_product(
    product_id: str,
    product_data: ProductUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a product (only by the seller)"""
    try:
        # Update the product
        updated_product = update_product(
            db=db, 
            product_id=product_id, 
            product_data=product_data, 
            seller_id=current_user.id
        )
        
        if not updated_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found or you don't have permission to update it"
            )
        
        logger.info(f"Product updated: {product_id} by {current_user.email}")
        
        return ProductResponse.from_orm(updated_product)
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Business logic error during product update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product"
        )

@router.delete("/{product_id}")
def delete_user_product(
    product_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a product (only by the seller)"""
    try:
        # Delete the product
        success = delete_product(db=db, product_id=product_id, seller_id=current_user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found or you don't have permission to delete it"
            )
        
        logger.info(f"Product deleted: {product_id} by {current_user.email}")
        
        return {"message": "Product deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete product"
        )

@router.patch("/{product_id}/stock", response_model=ProductResponse)
def update_product_stock_quantity(
    product_id: str,
    quantity_change: int,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update product stock quantity"""
    try:
        # Update stock
        updated_product = update_product_stock(
            db=db, 
            product_id=product_id, 
            quantity_change=quantity_change, 
            seller_id=current_user.id
        )
        
        if not updated_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found or you don't have permission to update it"
            )
        
        logger.info(f"Product stock updated: {product_id} by {current_user.email}")
        
        return ProductResponse.from_orm(updated_product)
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Business logic error during stock update: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating product stock: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product stock"
        )

@router.get("/my-stats")
def get_my_product_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get product statistics for current user."""
    try:
        from models.product import Product
        
        # Get statistics
        total_products = db.query(Product).filter(Product.seller_id == current_user.id).count()
        active_products = db.query(Product).filter(
            Product.seller_id == current_user.id,
            Product.is_active == True
        ).count()
        inactive_products = total_products - active_products
        
        # Low stock (assuming threshold of 10)
        low_stock_products = db.query(Product).filter(
            Product.seller_id == current_user.id,
            Product.stock_quantity <= 10,
            Product.stock_quantity > 0,
            Product.is_active == True
        ).count()
        
        # Out of stock
        out_of_stock_products = db.query(Product).filter(
            Product.seller_id == current_user.id,
            Product.stock_quantity <= 0,
            Product.is_active == True
        ).count()
        
        return success_response(
            data={
                "total_products": total_products,
                "active_products": active_products,
                "inactive_products": inactive_products,
                "low_stock_products": low_stock_products,
                "out_of_stock_products": out_of_stock_products
            },
            message="Product statistics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting product stats: {str(e)}")
        return error_response(
            message="Failed to retrieve product statistics",
            error_code="PRODUCT_STATS_ERROR",
            details={"error": str(e)}
        )

@router.get("/my-products")
def get_my_products(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get products for current user."""
    try:
        products = get_products_by_seller(
            db=db, 
            seller_id=current_user.id, 
            skip=skip, 
            limit=limit,
            active_only=active_only
        )
        
        if not products:
            return empty_data_response(
                data_type="products",
                reason="No products found for this user",
                suggestions=[
                    "Create your first product",
                    "Check your product filters",
                    "Contact support if this seems incorrect"
                ]
            )
        
        product_data = [ProductResponse.from_orm(product) for product in products]
        
        return success_response(
            data=product_data,
            message=f"Retrieved {len(product_data)} products successfully"
        )
        
    except Exception as e:
        logger.error(f"Error getting user products: {str(e)}")
        return error_response(
            message="Failed to retrieve products",
            error_code="PRODUCTS_RETRIEVAL_ERROR",
            details={"error": str(e)}
        )