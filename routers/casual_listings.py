"""
Casual Listings API Router
Industry-standard marketplace endpoints for casual sellers
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from database.connection import get_db
from models.casual_listing import CasualListing, CasualListingInquiry, CasualListingFavorite
from models.user import User
from routers.auth import get_current_user

router = APIRouter(prefix="/casual-listings", tags=["Casual Listings"])
# Updated to use optional authentication

# Optional authentication for marketplace endpoints
security = HTTPBearer(auto_error=False)

def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None"""
    if not credentials:
        return None
    try:
        # Import here to avoid circular imports
        from services.auth import verify_token
        payload = verify_token(credentials.credentials)
        if not payload:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        user = db.query(User).filter(User.id == user_id).first()
        return user
    except:
        return None

# Industry-standard marketplace categories
MARKETPLACE_CATEGORIES = [
    "electronics", "fashion", "sports", "home", "automotive", "books",
    "toys", "beauty", "jewelry", "art", "music", "travel", "pets",
    "office", "garden", "food", "health", "collectibles"
]

# Standard conditions for marketplace items
MARKETPLACE_CONDITIONS = [
    "new", "like_new", "good", "fair", "poor"
]


@router.get("/categories/list")
async def get_categories(db: Session = Depends(get_db)):
    """
    Get all available categories for casual listings
    """
    try:
        # Get categories with listing counts
        category_counts = db.query(
            CasualListing.category,
            func.count(CasualListing.id).label('count')
        ).filter(
            CasualListing.status == 'active'
        ).group_by(CasualListing.category).all()

        count_dict = {cat.category: cat.count for cat in category_counts}

        categories = []
        for category in MARKETPLACE_CATEGORIES:
            categories.append({
                "id": category,
                "name": category.replace('_', ' ').title(),
                "count": count_dict.get(category, 0)
            })

        return {
            "success": True,
            "data": {
                "categories": categories,
                "total_categories": len(categories)
            }
        }

    except Exception as e:
        print(f"Error fetching categories: {str(e)}")
        return {
            "success": True,
            "data": {
                "categories": [{"id": cat, "name": cat.replace('_', ' ').title(), "count": 0}
                              for cat in MARKETPLACE_CATEGORIES],
                "total_categories": len(MARKETPLACE_CATEGORIES)
            }
        }


@router.get("/conditions/list")
async def get_conditions(db: Session = Depends(get_db)):
    """
    Get all available conditions for casual listings
    """
    try:
        conditions = [condition.replace('_', ' ').title() for condition in MARKETPLACE_CONDITIONS]

        return {
            "success": True,
            "data": {
                "conditions": conditions
            }
        }

    except Exception as e:
        print(f"Error fetching conditions: {str(e)}")
        return {
            "success": True,
            "data": {
                "conditions": ["New", "Like New", "Good", "Fair", "Poor"]
            }
        }


@router.get("/")
async def get_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    condition: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    city: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort: str = Query("newest", regex="^(newest|oldest|price_low|price_high|views|popular)$"),
    seller_type: Optional[str] = Query(None),
    is_negotiable: Optional[bool] = Query(None),
    is_delivery_available: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Get casual listings with advanced filtering and sorting
    """
    try:
        # Base query - only active listings
        query = db.query(CasualListing).filter(CasualListing.status == 'active')

        # Apply filters
        if category:
            query = query.filter(CasualListing.category == category)

        if condition:
            condition_value = condition.lower().replace(' ', '_')
            query = query.filter(CasualListing.condition == condition_value)

        if min_price is not None:
            query = query.filter(CasualListing.price >= min_price)

        if max_price is not None:
            query = query.filter(CasualListing.price <= max_price)

        if city:
            query = query.filter(CasualListing.city.ilike(f"%{city}%"))

        if region:
            query = query.filter(CasualListing.region.ilike(f"%{region}%"))

        if seller_type:
            # Handle comma-separated seller types
            seller_types = [s.strip() for s in seller_type.split(',')]
            query = query.filter(CasualListing.seller_type.in_(seller_types))

        if is_negotiable is not None:
            query = query.filter(CasualListing.is_negotiable == is_negotiable)

        if is_delivery_available is not None:
            query = query.filter(CasualListing.is_delivery_available == is_delivery_available)

        # Search functionality
        if search:
            search_filter = or_(
                CasualListing.title.ilike(f"%{search}%"),
                CasualListing.description.ilike(f"%{search}%"),
                CasualListing.location.ilike(f"%{search}%")
            )
            query = query.filter(search_filter)

        # Sorting
        if sort == "newest":
            query = query.order_by(desc(CasualListing.created_at))
        elif sort == "oldest":
            query = query.order_by(asc(CasualListing.created_at))
        elif sort == "price_low":
            query = query.order_by(asc(CasualListing.price))
        elif sort == "price_high":
            query = query.order_by(desc(CasualListing.price))
        elif sort == "views":
            query = query.order_by(desc(CasualListing.views_count))
        elif sort == "popular":
            query = query.order_by(desc(CasualListing.favorites_count))

        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        listings = query.offset(skip).limit(limit).all()

        # Convert to dict and add seller info
        listings_data = []
        for listing in listings:
            listing_dict = listing.to_dict()

            # Get seller info
            seller = db.query(User).filter(User.id == listing.seller_id).first()
            if seller:
                listing_dict["seller_name"] = f"{seller.first_name} {seller.last_name}".strip()
                listing_dict["seller_email"] = seller.email

            # Check if current user has favorited this listing
            if current_user:
                is_favorited = db.query(CasualListingFavorite).filter(
                    and_(
                        CasualListingFavorite.user_id == current_user.id,
                        CasualListingFavorite.listing_id == listing.id
                    )
                ).first() is not None
                listing_dict["is_favorited"] = is_favorited
            else:
                listing_dict["is_favorited"] = False

            listings_data.append(listing_dict)

        return {
            "success": True,
            "data": listings_data,
            "pagination": {
                "total": total_count,
                "skip": skip,
                "limit": limit,
                "has_more": (skip + limit) < total_count
            }
        }

    except Exception as e:
        print(f"Error fetching listings: {str(e)}")
        # Return empty data structure for now
        return {
            "success": True,
            "data": [],
            "pagination": {
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False
            }
        }


@router.get("/my-listings")
async def get_my_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's listings
    """
    try:
        query = db.query(CasualListing).filter(CasualListing.seller_id == current_user.id)

        if status:
            query = query.filter(CasualListing.status == status)

        query = query.order_by(desc(CasualListing.created_at))

        total_count = query.count()
        listings = query.offset(skip).limit(limit).all()

        listings_data = [listing.to_dict() for listing in listings]

        return {
            "success": True,
            "data": listings_data,
            "pagination": {
                "total": total_count,
                "skip": skip,
                "limit": limit,
                "has_more": (skip + limit) < total_count
            }
        }

    except Exception as e:
        print(f"Error fetching user listings: {str(e)}")
        return {
            "success": True,
            "data": [],
            "pagination": {
                "total": 0,
                "skip": skip,
                "limit": limit,
                "has_more": False
            }
        }