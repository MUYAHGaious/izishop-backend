from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, and_, or_
from fastapi import HTTPException, status
from datetime import datetime, timedelta

from models.rating import Rating, RatingHelpfulness, RatingFlag, ShopStats
from models.shop import Shop
from models.user import User
from models.order import Order  # Assuming this exists for verified purchase check
from schemas.rating import (
    RatingCreate, RatingUpdate, RatingWithUser, PaginatedRatings,
    ShopRatingStats, RatingHelpfulnessCreate, RatingFlagCreate,
    AdminRatingAction, ShopReviewSummary
)

class RatingService:
    
    @staticmethod
    def create_rating(
        db: Session, 
        shop_id: str, 
        user_id: str, 
        rating_data: RatingCreate
    ) -> Rating:
        """Create a new rating for a shop"""
        
        # Check if shop exists
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shop not found"
            )
        
        # Check if user already rated this shop
        existing_rating = db.query(Rating).filter(
            and_(Rating.shop_id == shop_id, Rating.user_id == user_id)
        ).first()
        
        if existing_rating:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You have already rated this shop. Use PUT to update your rating."
            )
        
        # Check if user made a purchase from this shop (optional verification)
        is_verified_purchase = RatingService._check_verified_purchase(db, user_id, shop_id)
        
        # Create rating
        rating = Rating(
            shop_id=shop_id,
            user_id=user_id,
            rating=rating_data.rating,
            review=rating_data.review,
            is_verified_purchase=is_verified_purchase
        )
        
        db.add(rating)
        db.commit()
        db.refresh(rating)
        
        # Update shop statistics
        RatingService._update_shop_rating_stats(db, shop_id)
        
        return rating
    
    @staticmethod
    def update_rating(
        db: Session,
        rating_id: str,
        user_id: str,
        rating_data: RatingUpdate
    ) -> Rating:
        """Update an existing rating"""
        
        rating = db.query(Rating).filter(
            and_(Rating.id == rating_id, Rating.user_id == user_id)
        ).first()
        
        if not rating:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Rating not found or you don't have permission to update it"
            )
        
        # Update fields
        if rating_data.rating is not None:
            rating.rating = rating_data.rating
        if rating_data.review is not None:
            rating.review = rating_data.review
        
        rating.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(rating)
        
        # Update shop statistics
        RatingService._update_shop_rating_stats(db, rating.shop_id)
        
        return rating
    
    @staticmethod
    def get_shop_ratings(
        db: Session,
        shop_id: str,
        page: int = 1,
        page_size: int = 10,
        sort_by: str = "newest",
        min_rating: Optional[int] = None,
        verified_only: bool = False
    ) -> PaginatedRatings:
        """Get paginated ratings for a shop"""
        
        query = db.query(Rating).options(
            joinedload(Rating.user)
        ).filter(
            and_(Rating.shop_id == shop_id, Rating.is_active == True)
        )
        
        # Apply filters
        if min_rating:
            query = query.filter(Rating.rating >= min_rating)
        
        if verified_only:
            query = query.filter(Rating.is_verified_purchase == True)
        
        # Apply sorting
        if sort_by == "newest":
            query = query.order_by(desc(Rating.created_at))
        elif sort_by == "oldest":
            query = query.order_by(Rating.created_at)
        elif sort_by == "highest":
            query = query.order_by(desc(Rating.rating), desc(Rating.created_at))
        elif sort_by == "lowest":
            query = query.order_by(Rating.rating, desc(Rating.created_at))
        elif sort_by == "helpful":
            query = query.order_by(desc(Rating.helpful_count), desc(Rating.created_at))
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * page_size
        ratings = query.offset(offset).limit(page_size).all()
        
        # Convert to response format
        rating_responses = []
        for rating in ratings:
            rating_data = RatingWithUser(
                id=rating.id,
                user_id=rating.user_id,
                shop_id=rating.shop_id,
                rating=rating.rating,
                review=rating.review,
                is_verified_purchase=rating.is_verified_purchase,
                helpful_count=rating.helpful_count,
                not_helpful_count=rating.not_helpful_count,
                created_at=rating.created_at,
                updated_at=rating.updated_at,
                user_name=f"{rating.user.first_name} {rating.user.last_name[0]}.",
                user_first_name=rating.user.first_name,
                user_profile_image=rating.user.profile_image_url
            )
            rating_responses.append(rating_data)
        
        total_pages = (total + page_size - 1) // page_size
        
        return PaginatedRatings(
            ratings=rating_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )
    
    @staticmethod
    def get_shop_rating_stats(db: Session, shop_id: str) -> ShopRatingStats:
        """Get rating statistics for a shop"""
        
        rating_data = Rating.get_shop_average_rating(db, shop_id)
        distribution = Rating.get_rating_distribution(db, shop_id)
        
        return ShopRatingStats(
            average_rating=rating_data['average_rating'],
            total_reviews=rating_data['total_reviews'],
            rating_distribution=distribution
        )
    
    @staticmethod
    def get_shop_review_summary(db: Session, shop_id: str) -> ShopReviewSummary:
        """Get comprehensive review summary for a shop"""
        
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            raise HTTPException(status_code=404, detail="Shop not found")
        
        # Get basic stats
        stats = RatingService.get_shop_rating_stats(db, shop_id)
        
        # Get recent reviews (last 5)
        recent_ratings = RatingService.get_shop_ratings(
            db, shop_id, page=1, page_size=5, sort_by="newest"
        )
        
        # Calculate verified purchase percentage
        total_reviews = stats.total_reviews
        verified_reviews = db.query(Rating).filter(
            and_(
                Rating.shop_id == shop_id,
                Rating.is_verified_purchase == True,
                Rating.is_active == True
            )
        ).count()
        
        verified_percentage = (verified_reviews / total_reviews * 100) if total_reviews > 0 else 0
        
        return ShopReviewSummary(
            shop_id=shop_id,
            shop_name=shop.name,
            average_rating=stats.average_rating,
            total_reviews=stats.total_reviews,
            rating_distribution=stats.rating_distribution,
            recent_reviews=recent_ratings.ratings,
            verified_purchase_percentage=round(verified_percentage, 1)
        )
    
    @staticmethod
    def mark_rating_helpful(
        db: Session,
        rating_id: str,
        user_id: str,
        helpfulness_data: RatingHelpfulnessCreate
    ) -> bool:
        """Mark a rating as helpful or not helpful"""
        
        # Check if rating exists
        rating = db.query(Rating).filter(Rating.id == rating_id).first()
        if not rating:
            raise HTTPException(status_code=404, detail="Rating not found")
        
        # Check if user already voted
        existing_vote = db.query(RatingHelpfulness).filter(
            and_(
                RatingHelpfulness.rating_id == rating_id,
                RatingHelpfulness.user_id == user_id
            )
        ).first()
        
        if existing_vote:
            # Update existing vote
            old_helpful = existing_vote.is_helpful
            existing_vote.is_helpful = helpfulness_data.is_helpful
            
            # Update counts
            if old_helpful != helpfulness_data.is_helpful:
                if helpfulness_data.is_helpful:
                    rating.helpful_count += 1
                    rating.not_helpful_count -= 1
                else:
                    rating.helpful_count -= 1
                    rating.not_helpful_count += 1
        else:
            # Create new vote
            vote = RatingHelpfulness(
                rating_id=rating_id,
                user_id=user_id,
                is_helpful=helpfulness_data.is_helpful
            )
            db.add(vote)
            
            # Update counts
            if helpfulness_data.is_helpful:
                rating.helpful_count += 1
            else:
                rating.not_helpful_count += 1
        
        db.commit()
        return True
    
    @staticmethod
    def flag_rating(
        db: Session,
        rating_id: str,
        user_id: str,
        flag_data: RatingFlagCreate
    ) -> bool:
        """Flag a rating for moderation"""
        
        # Check if rating exists
        rating = db.query(Rating).filter(Rating.id == rating_id).first()
        if not rating:
            raise HTTPException(status_code=404, detail="Rating not found")
        
        # Check if user already flagged this rating
        existing_flag = db.query(RatingFlag).filter(
            and_(
                RatingFlag.rating_id == rating_id,
                RatingFlag.user_id == user_id
            )
        ).first()
        
        if existing_flag:
            raise HTTPException(
                status_code=400,
                detail="You have already flagged this rating"
            )
        
        # Create flag
        flag = RatingFlag(
            rating_id=rating_id,
            user_id=user_id,
            reason=flag_data.reason,
            description=flag_data.description
        )
        
        db.add(flag)
        
        # Mark rating as flagged if it receives multiple flags
        flag_count = db.query(RatingFlag).filter(
            RatingFlag.rating_id == rating_id
        ).count() + 1
        
        if flag_count >= 3:  # Auto-flag after 3 reports
            rating.is_flagged = True
        
        db.commit()
        return True
    
    @staticmethod
    def delete_rating(db: Session, rating_id: str, user_id: str) -> bool:
        """Delete a rating (soft delete)"""
        
        rating = db.query(Rating).filter(
            and_(Rating.id == rating_id, Rating.user_id == user_id)
        ).first()
        
        if not rating:
            raise HTTPException(
                status_code=404,
                detail="Rating not found or you don't have permission to delete it"
            )
        
        rating.is_active = False
        db.commit()
        
        # Update shop statistics
        RatingService._update_shop_rating_stats(db, rating.shop_id)
        
        return True
    
    @staticmethod
    def _check_verified_purchase(db: Session, user_id: str, shop_id: str) -> bool:
        """Check if user has made a purchase from the shop"""
        # This assumes you have an Order model with shop relationship
        # Modify based on your actual order/purchase structure
        try:
            # Simple check - you might want to add more criteria like completed orders only
            purchase = db.query(Order).join(Shop).filter(
                and_(
                    Order.customer_id == user_id,
                    Shop.id == shop_id,
                    Order.status == "completed"  # Adjust based on your order status enum
                )
            ).first()
            return purchase is not None
        except:
            # If Order model doesn't exist or has different structure, return False
            return False
    
    @staticmethod
    def _update_shop_rating_stats(db: Session, shop_id: str):
        """Update shop's cached rating statistics"""
        
        rating_data = Rating.get_shop_average_rating(db, shop_id)
        
        # Update shop's direct rating fields
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if shop:
            shop.average_rating = rating_data['average_rating']
            shop.total_reviews = rating_data['total_reviews']
        
        # Update detailed stats
        ShopStats.update_rating_stats(db, shop_id)
        
        db.commit()

# Admin service for moderation
class AdminRatingService:
    
    @staticmethod
    def get_flagged_ratings(db: Session, page: int = 1, page_size: int = 20):
        """Get flagged ratings for admin review"""
        
        query = db.query(Rating).options(
            joinedload(Rating.user),
            joinedload(Rating.shop),
            joinedload(Rating.flags)
        ).filter(
            or_(Rating.is_flagged == True, Rating.flags.any())
        )
        
        total = query.count()
        offset = (page - 1) * page_size
        ratings = query.offset(offset).limit(page_size).all()
        
        return {
            "ratings": ratings,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    
    @staticmethod
    def moderate_rating(
        db: Session,
        rating_id: str,
        action_data: AdminRatingAction
    ) -> bool:
        """Take moderation action on a rating"""
        
        rating = db.query(Rating).filter(Rating.id == rating_id).first()
        if not rating:
            raise HTTPException(status_code=404, detail="Rating not found")
        
        if action_data.action == "approve":
            rating.is_flagged = False
            rating.is_active = True
        elif action_data.action == "hide":
            rating.is_active = False
        elif action_data.action == "delete":
            db.delete(rating)
        elif action_data.action == "warn_user":
            rating.is_flagged = False
            # You might want to send a warning email to the user here
        
        if action_data.admin_notes:
            rating.admin_notes = action_data.admin_notes
        
        # Mark related flags as resolved
        db.query(RatingFlag).filter(
            RatingFlag.rating_id == rating_id
        ).update({
            "is_resolved": True,
            "admin_action": action_data.action,
            "resolved_at": datetime.utcnow()
        })
        
        db.commit()
        
        # Update shop stats if rating was hidden/deleted
        if action_data.action in ["hide", "delete"]:
            RatingService._update_shop_rating_stats(db, rating.shop_id)
        
        return True