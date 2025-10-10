from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging

from database.connection import get_db
from core.exceptions import ResourceNotFoundError, BusinessLogicError
from schemas.user import UserResponse
from routers.auth import get_current_user
from models.user import UserRole
from models.review import Review
from models.product import Product
from models.user import User
from sqlalchemy import and_, func, desc

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/featured")
async def get_featured_reviews(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """Get featured reviews for landing page"""
    try:
        # Get reviews with highest helpful counts and ratings
        reviews = db.query(Review).filter(
            and_(
                Review.is_active == True,
                Review.rating >= 4,
                Review.helpful_count > 0
            )
        ).order_by(
            desc(Review.helpful_count),
            desc(Review.rating),
            desc(Review.created_at)
        ).limit(limit).all()
        
        # Add user and product information
        result = []
        for review in reviews:
            user = db.query(User).filter(User.id == review.user_id).first()
            product = db.query(Product).filter(Product.id == review.product_id).first()
            
            result.append({
                "id": review.id,
                "user_name": f"{user.first_name} {user.last_name}" if user else "Anonymous",
                "user_avatar": None,  # TODO: Add user avatar field
                "rating": review.rating,
                "title": review.title,
                "content": review.comment,
                "product_name": product.name if product else "Product",
                "shop_name": product.shop.name if product and product.shop else "Shop",
                "created_at": review.created_at.isoformat(),
                "is_verified_purchase": review.is_verified_purchase,
                "helpful_count": review.helpful_count
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting featured reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve featured reviews"
        )

@router.get("/top-rated-products")
async def get_top_rated_products(
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """Get top-rated products for landing page"""
    try:
        # Get products with highest average ratings and review counts
        products = db.query(Product).join(Review).filter(
            and_(
                Product.is_active == True,
                Review.is_active == True
            )
        ).group_by(Product.id).having(
            func.count(Review.id) >= 3  # At least 3 reviews
        ).order_by(
            desc(func.avg(Review.rating)),
            desc(func.count(Review.id))
        ).limit(limit).all()
        
        result = []
        for product in products:
            # Get review stats for each product
            review_stats = db.query(
                func.avg(Review.rating).label('avg_rating'),
                func.count(Review.id).label('review_count')
            ).filter(
                and_(
                    Review.product_id == product.id,
                    Review.is_active == True
                )
            ).first()
            
            result.append({
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "image_url": product.image_url,
                "shop_name": product.shop.name if product.shop else "Shop",
                "average_rating": float(review_stats.avg_rating) if review_stats.avg_rating else 0,
                "review_count": review_stats.review_count or 0
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting top-rated products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve top-rated products"
        )

@router.post("/{review_id}/helpful")
async def mark_review_helpful(
    review_id: str,
    helpful: bool = True,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a review as helpful or not helpful"""
    try:
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            raise ResourceNotFoundError("Review not found")
        
        # TODO: Implement helpful voting system with user tracking
        # For now, just increment/decrement helpful count
        if helpful:
            review.helpful_count += 1
        else:
            review.helpful_count = max(0, review.helpful_count - 1)
        
        db.commit()
        db.refresh(review)
        
        return {"success": True, "helpful_count": review.helpful_count}
        
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error marking review helpful: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark review as helpful"
        )

@router.get("/pending")
async def get_pending_reviews(
    shop_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get pending reviews for moderation (Admin/Shop Owner only)"""
    try:
        # Check if user is admin or shop owner
        if current_user.role not in [UserRole.ADMIN, UserRole.SHOP_OWNER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        query = db.query(Review).filter(Review.is_active == False)
        
        # If shop owner, filter by their shop
        if current_user.role == UserRole.SHOP_OWNER and shop_id:
            query = query.join(Product).filter(Product.shop_id == shop_id)
        
        # Apply pagination
        skip = (page - 1) * limit
        reviews = query.offset(skip).limit(limit).all()
        
        # Add user and product information
        result = []
        for review in reviews:
            user = db.query(User).filter(User.id == review.user_id).first()
            product = db.query(Product).filter(Product.id == review.product_id).first()
            
            result.append({
                "id": review.id,
                "user_name": f"{user.first_name} {user.last_name}" if user else "Anonymous",
                "rating": review.rating,
                "title": review.title,
                "content": review.comment,
                "product_name": product.name if product else "Product",
                "shop_name": product.shop.name if product and product.shop else "Shop",
                "created_at": review.created_at.isoformat(),
                "is_verified_purchase": review.is_verified_purchase
            })
        
        return {
            "reviews": result,
            "page": page,
            "limit": limit,
            "total": query.count()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting pending reviews: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pending reviews"
        )

@router.post("/{review_id}/approve")
async def approve_review(
    review_id: str,
    approved: bool = True,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Approve or reject a review (Admin/Shop Owner only)"""
    try:
        # Check if user is admin or shop owner
        if current_user.role not in [UserRole.ADMIN, UserRole.SHOP_OWNER]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            raise ResourceNotFoundError("Review not found")
        
        # If shop owner, check if they own the product
        if current_user.role == UserRole.SHOP_OWNER:
            product = db.query(Product).filter(Product.id == review.product_id).first()
            if not product or product.shop.owner_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You can only moderate reviews for your own products"
                )
        
        review.is_active = approved
        db.commit()
        db.refresh(review)
        
        return {"success": True, "approved": approved}
        
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve review"
        )

@router.post("/{review_id}/respond")
async def respond_to_review(
    review_id: str,
    response: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Respond to a review (Shop Owner only)"""
    try:
        # Check if user is shop owner
        if current_user.role != UserRole.SHOP_OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only shop owners can respond to reviews"
            )
        
        review = db.query(Review).filter(Review.id == review_id).first()
        if not review:
            raise ResourceNotFoundError("Review not found")
        
        # Check if user owns the product
        product = db.query(Product).filter(Product.id == review.product_id).first()
        if not product or product.shop.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only respond to reviews for your own products"
            )
        
        # TODO: Add seller_response field to Review model
        # For now, we'll add it as a comment or note
        review.seller_response = response
        review.seller_response_date = func.now()
        
        db.commit()
        db.refresh(review)
        
        return {"success": True, "response": response}
        
    except ResourceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error responding to review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to respond to review"
        )
