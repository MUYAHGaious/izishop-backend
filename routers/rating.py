from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database.session import get_db
from services.auth import get_current_user, get_admin_user
from services.rating import RatingService, AdminRatingService
from schemas.rating import (
    RatingCreate, RatingUpdate, RatingResponse, RatingWithUser,
    PaginatedRatings, ShopRatingStats, ShopReviewSummary,
    RatingHelpfulnessCreate, RatingFlagCreate, AdminRatingAction
)
from schemas.user import UserResponse

router = APIRouter(prefix="/api", tags=["ratings"])

# Public endpoints
@router.get("/shops/{shop_id}/ratings", response_model=PaginatedRatings)
def get_shop_ratings(
    shop_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    sort_by: str = Query("newest", regex="^(newest|oldest|highest|lowest|helpful)$"),
    min_rating: Optional[int] = Query(None, ge=1, le=5),
    verified_only: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get paginated ratings for a shop"""
    return RatingService.get_shop_ratings(
        db=db,
        shop_id=shop_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        min_rating=min_rating,
        verified_only=verified_only
    )

@router.get("/shops/{shop_id}/rating-stats", response_model=ShopRatingStats)
def get_shop_rating_stats(shop_id: str, db: Session = Depends(get_db)):
    """Get rating statistics for a shop"""
    return RatingService.get_shop_rating_stats(db=db, shop_id=shop_id)

@router.get("/shops/{shop_id}/review-summary", response_model=ShopReviewSummary)
def get_shop_review_summary(shop_id: str, db: Session = Depends(get_db)):
    """Get comprehensive review summary for a shop"""
    return RatingService.get_shop_review_summary(db=db, shop_id=shop_id)

# Authenticated endpoints
@router.post("/shops/{shop_id}/ratings", response_model=RatingResponse, status_code=status.HTTP_201_CREATED)
def create_rating(
    shop_id: str,
    rating_data: RatingCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit a rating and review for a shop"""
    
    # Prevent users from rating their own shop
    from models.shop import Shop
    shop = db.query(Shop).filter(Shop.id == shop_id).first()
    if shop and shop.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot rate your own shop"
        )
    
    return RatingService.create_rating(
        db=db,
        shop_id=shop_id,
        user_id=current_user.id,
        rating_data=rating_data
    )

@router.put("/ratings/{rating_id}", response_model=RatingResponse)
def update_rating(
    rating_id: str,
    rating_data: RatingUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update your existing rating"""
    return RatingService.update_rating(
        db=db,
        rating_id=rating_id,
        user_id=current_user.id,
        rating_data=rating_data
    )

@router.delete("/ratings/{rating_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rating(
    rating_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete your rating"""
    RatingService.delete_rating(
        db=db,
        rating_id=rating_id,
        user_id=current_user.id
    )

@router.post("/ratings/{rating_id}/helpful", status_code=status.HTTP_201_CREATED)
def mark_rating_helpful(
    rating_id: str,
    helpfulness_data: RatingHelpfulnessCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark a rating as helpful or not helpful"""
    return RatingService.mark_rating_helpful(
        db=db,
        rating_id=rating_id,
        user_id=current_user.id,
        helpfulness_data=helpfulness_data
    )

@router.post("/ratings/{rating_id}/flag", status_code=status.HTTP_201_CREATED)
def flag_rating(
    rating_id: str,
    flag_data: RatingFlagCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Flag a rating for moderation"""
    return RatingService.flag_rating(
        db=db,
        rating_id=rating_id,
        user_id=current_user.id,
        flag_data=flag_data
    )

# User's rating history
@router.get("/users/my-ratings", response_model=List[RatingResponse])
def get_my_ratings(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's rating history"""
    from models.rating import Rating
    ratings = db.query(Rating).filter(
        Rating.user_id == current_user.id
    ).order_by(Rating.created_at.desc()).all()
    return ratings

# Admin endpoints
@router.get("/admin/ratings/flagged")
def get_flagged_ratings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserResponse = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Get flagged ratings for admin review"""
    return AdminRatingService.get_flagged_ratings(
        db=db,
        page=page,
        page_size=page_size
    )

@router.post("/admin/ratings/{rating_id}/moderate")
def moderate_rating(
    rating_id: str,
    action_data: AdminRatingAction,
    current_user: UserResponse = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Take moderation action on a rating"""
    return AdminRatingService.moderate_rating(
        db=db,
        rating_id=rating_id,
        action_data=action_data
    )

# Shop owner endpoints - to see ratings for their shops
@router.get("/shop-owner/ratings", response_model=PaginatedRatings)
def get_my_shop_ratings(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    sort_by: str = Query("newest", regex="^(newest|oldest|highest|lowest|helpful)$"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get ratings for shop owner's shop"""
    
    # Check if user is a shop owner and get their shop
    from models.shop import Shop
    shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found. You must be a shop owner to access this endpoint."
        )
    
    return RatingService.get_shop_ratings(
        db=db,
        shop_id=shop.id,
        page=page,
        page_size=page_size,
        sort_by=sort_by
    )

@router.get("/shop-owner/rating-stats", response_model=ShopRatingStats)
def get_my_shop_rating_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get rating statistics for shop owner's shop"""
    
    from models.shop import Shop
    shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found"
        )
    
    return RatingService.get_shop_rating_stats(db=db, shop_id=shop.id)