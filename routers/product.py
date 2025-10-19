from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import base64
import binascii
import json

from database.connection import get_db
from core.response import success_response, empty_data_response, error_response
from core.exceptions import ResourceNotFoundError, BusinessLogicError
from sqlalchemy import func
from services.product import (
    create_product,
    get_product_by_id,
    get_products_by_seller,
    get_all_products,
    get_products_for_catalog,
    search_products,
    update_product,
    delete_product,
    get_seller_product_stats,
    update_product_stock,
    create_product_review,
    get_product_reviews,
    get_product_review_stats,
    get_related_products
)
from schemas.product import (
    ProductCreate, 
    ProductUpdate, 
    ProductResponse, 
    ProductListResponse,
    ProductReviewCreate,
    ProductReviewResponse,
    ProductReviewListResponse,
    ProductReviewStats
)
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

@router.get("/")
def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),  # Reduced max limit to save memory
    active_only: bool = Query(True),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    # New optional filters for server-side support
    categories: Optional[List[str]] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    # Accepted but currently unused: brands, features
    brands: Optional[List[str]] = Query(None),
    features: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db)
):
    """Get all products (memory-optimized public endpoint for product catalog)"""
    logger.info(f"🌐 GET /products endpoint called with params: skip={skip}, limit={limit}, active_only={active_only}, search={search}, category={category}")

    try:
        if search:
            # Search with filters
            logger.info(f"🔍 Using search functionality with term: {search}")
            products = search_products(
                db=db,
                search_term=search,
                skip=skip,
                limit=min(limit, 20),
                category=category,
                categories=categories,
                min_price=min_price,
                max_price=max_price,
                min_rating=min_rating,
            )
            response_data = [ProductResponse.from_orm(product) for product in products]
            logger.info(f"📤 Search response: {len(response_data)} products returned")
            return response_data
        else:
            # Memory-efficient catalog with filters
            logger.info(f"📋 Using catalog functionality")
            result = get_products_for_catalog(
                db=db,
                skip=skip,
                limit=limit,
                active_only=active_only,
                category=category,
                categories=categories,
                min_price=min_price,
                max_price=max_price,
                min_rating=min_rating,
            )

            response_data = result['products']
            logger.info(f"📤 Catalog response: {len(response_data)} products returned from get_products_for_catalog")
            logger.info(f"📦 Response metadata: total_count={result.get('total_count')}, page={result.get('page')}, has_more={result.get('has_more')}")

            # Log first product in response for debugging
            if response_data:
                first_product = response_data[0]
                logger.info(f"📝 First product in response: id={first_product.get('id', 'N/A')}, name={first_product.get('name', 'N/A')}, image_url={first_product.get('image_url', 'N/A')}")
            else:
                logger.warning(f"⚠️ Empty response data returned to client")

            return response_data  # Return the lite products directly

    except Exception as e:
        logger.error(f"❌ Error getting products: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve products"
        )

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: str, db: Session = Depends(get_db)):
    """Get a specific product by ID (public endpoint)"""
    try:
        from models.shop import Shop
        from models.user import User
        from schemas.product import ShopInfo

        product = get_product_by_id(db=db, product_id=product_id)

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )

        # Load shop information including owner_id
        shop = db.query(Shop).filter(Shop.owner_id == product.seller_id).first()

        product_response = ProductResponse.from_orm(product)

        if shop:
            product_response.shop = ShopInfo(
                id=shop.id,
                owner_id=shop.owner_id,  # This is the key field we need!
                name=shop.name,
                verified=shop.verified if hasattr(shop, 'verified') else False,
                rating=shop.rating if hasattr(shop, 'rating') else None,
                total_reviews=shop.total_reviews if hasattr(shop, 'total_reviews') else 0,
                location=shop.location if hasattr(shop, 'location') else None
            )
        else:
            # No shop - get seller's user info for individual sellers
            seller = db.query(User).filter(User.id == product.seller_id).first()
            if seller:
                # Add seller_name to product response using first_name and last_name
                product_response.seller_name = f"{seller.first_name} {seller.last_name}".strip() if seller.first_name or seller.last_name else None

        return product_response

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

@router.get("/{product_id}/reviews", response_model=List[ProductReviewResponse])
def get_product_reviews_endpoint(
    product_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    sort_by: str = Query("newest", regex="^(newest|oldest|highest|lowest|helpful)$"),
    db: Session = Depends(get_db)
):
    """Get reviews for a specific product"""
    try:
        reviews = get_product_reviews(
            db=db, 
            product_id=product_id, 
            skip=skip, 
            limit=limit,
            sort_by=sort_by
        )
        return reviews
    except Exception as e:
        logger.error(f"Error getting product reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product reviews"
        )

@router.get("/{product_id}/reviews/stats", response_model=ProductReviewStats)
def get_product_review_stats_endpoint(
    product_id: str,
    db: Session = Depends(get_db)
):
    """Get review statistics for a specific product"""
    try:
        stats = get_product_review_stats(db=db, product_id=product_id)
        return stats
    except Exception as e:
        logger.error(f"Error getting product review stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product review statistics"
        )

@router.post("/{product_id}/reviews", response_model=ProductReviewResponse, status_code=status.HTTP_201_CREATED)
def create_product_review_endpoint(
    product_id: str,
    review_data: ProductReviewCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new review for a product"""
    try:
        review = create_product_review(
            db=db,
            product_id=product_id,
            user_id=current_user.id,
            review_data=review_data.model_dump()
        )
        return ProductReviewResponse.from_orm(review)
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except BusinessLogicError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating product review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product review"
        )

@router.get("/{product_id}/related", response_model=List[ProductResponse])
def get_related_products_endpoint(
    product_id: str,
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """Get related products for a specific product"""
    try:
        related_products = get_related_products(
            db=db, 
            product_id=product_id, 
            limit=limit
        )
        return [ProductResponse.from_orm(product) for product in related_products]
    except Exception as e:
        logger.error(f"Error getting related products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve related products"
        )

@router.get("/{product_id}/image/{image_index}")
async def get_product_image(
    product_id: str,
    image_index: int,
    db: Session = Depends(get_db)
):
    """Get a specific product image by index"""
    try:
        product = get_product_by_id(db, product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        if not product.image_urls:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No images found for this product"
            )
        
        # Parse image URLs
        try:
            if isinstance(product.image_urls, str):
                urls = json.loads(product.image_urls)
            else:
                urls = product.image_urls
        except:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid image data format"
            )
        
        if image_index >= len(urls):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Image index out of range"
            )
        
        image_url = urls[image_index]
        
        # Handle base64 images
        if image_url.startswith('data:'):
            try:
                # Extract base64 data
                header, data = image_url.split(',', 1)
                # Ensure header indicates base64
                if ';base64' not in header:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid data URL format"
                    )

                # Extract content type
                content_type = header.split(':')[1].split(';')[0]

                # Enforce a sane size limit (e.g., 5 MB) to avoid abuse
                approx_bytes = (len(data) * 3) // 4
                if approx_bytes > 5 * 1024 * 1024:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="Image too large"
                    )

                # Decode base64 safely (validate padding and alphabet)
                image_data = base64.b64decode(data, validate=True)

                return Response(
                    content=image_data,
                    media_type=content_type,
                    headers={"Cache-Control": "public, max-age=3600"}
                )
            except (ValueError, binascii.Error):
                # Invalid base64 content
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid base64 image data"
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error decoding base64 image: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to process image"
                )
        else:
            # For regular URLs, return a proper redirect response
            return RedirectResponse(url=image_url, status_code=status.HTTP_302_FOUND)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product image: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve product image"
        )
