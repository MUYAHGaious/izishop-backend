"""
Casual Listings API - Free marketplace for individual sellers
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.casual_listing import CasualListing
from schemas.casual_listing import (
    CasualListingCreate, 
    CasualListingResponse, 
    CasualListingUpdate,
    CasualListingSearch
)
import uuid
from decimal import Decimal

router = APIRouter(prefix="/api/casual-listings", tags=["casual-listings"])
logger = logging.getLogger(__name__)

@router.post("/", response_model=CasualListingResponse)
async def create_casual_listing(
    listing_data: CasualListingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new casual listing"""
    try:
        # Verify user can create casual listings
        if current_user.role not in ['CASUAL_SELLER', 'SHOP_OWNER']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only casual sellers and shop owners can create listings"
            )
        
        # Create new listing
        new_listing = CasualListing(
            id=str(uuid.uuid4()),
            seller_id=current_user.id,
            title=listing_data.title,
            description=listing_data.description,
            price=listing_data.price,
            condition=listing_data.condition,
            category=listing_data.category,
            location=listing_data.location,
            is_negotiable=listing_data.is_negotiable,
            images=listing_data.images or [],
            tags=listing_data.tags or [],
            is_active=True,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(new_listing)
        db.commit()
        db.refresh(new_listing)
        
        logger.info(f"Casual listing created: {new_listing.id} by user {current_user.id}")
        
        return CasualListingResponse.from_orm(new_listing)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating casual listing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create listing"
        )

@router.get("/", response_model=List[CasualListingResponse])
async def get_casual_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    condition: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get casual listings with optional filters"""
    try:
        query = db.query(CasualListing).filter(CasualListing.is_active == True)
        
        # Apply filters
        if category:
            query = query.filter(CasualListing.category == category)
        
        if condition:
            query = query.filter(CasualListing.condition == condition)
            
        if min_price is not None:
            query = query.filter(CasualListing.price >= min_price)
            
        if max_price is not None:
            query = query.filter(CasualListing.price <= max_price)
            
        if location:
            query = query.filter(CasualListing.location.ilike(f"%{location}%"))
            
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    CasualListing.title.ilike(search_term),
                    CasualListing.description.ilike(search_term),
                    CasualListing.tags.contains([search])
                )
            )
        
        # Order by creation date (newest first)
        listings = query.order_by(desc(CasualListing.created_at)).offset(skip).limit(limit).all()
        
        return [CasualListingResponse.from_orm(listing) for listing in listings]
        
    except Exception as e:
        logger.error(f"Error fetching casual listings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch listings"
        )

@router.get("/my-listings", response_model=List[CasualListingResponse])
async def get_my_casual_listings(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's casual listings"""
    try:
        listings = db.query(CasualListing).filter(
            CasualListing.seller_id == current_user.id
        ).order_by(desc(CasualListing.created_at)).offset(skip).limit(limit).all()
        
        return [CasualListingResponse.from_orm(listing) for listing in listings]
        
    except Exception as e:
        logger.error(f"Error fetching user's listings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch your listings"
        )

@router.get("/{listing_id}", response_model=CasualListingResponse)
async def get_casual_listing(
    listing_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific casual listing by ID"""
    try:
        listing = db.query(CasualListing).filter(
            and_(
                CasualListing.id == listing_id,
                CasualListing.is_active == True
            )
        ).first()
        
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Listing not found"
            )
            
        # Increment views (casual analytics)
        listing.views += 1
        db.commit()
        
        return CasualListingResponse.from_orm(listing)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching listing {listing_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch listing"
        )

@router.put("/{listing_id}", response_model=CasualListingResponse)
async def update_casual_listing(
    listing_id: str,
    listing_data: CasualListingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a casual listing (owner only)"""
    try:
        listing = db.query(CasualListing).filter(
            CasualListing.id == listing_id
        ).first()
        
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Listing not found"
            )
            
        if listing.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only update your own listings"
            )
        
        # Update fields
        update_data = listing_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(listing, field, value)
            
        listing.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(listing)
        
        logger.info(f"Casual listing updated: {listing_id} by user {current_user.id}")
        
        return CasualListingResponse.from_orm(listing)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating listing {listing_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update listing"
        )

@router.delete("/{listing_id}")
async def delete_casual_listing(
    listing_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete/deactivate a casual listing (owner only)"""
    try:
        listing = db.query(CasualListing).filter(
            CasualListing.id == listing_id
        ).first()
        
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Listing not found"
            )
            
        if listing.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own listings"
            )
        
        # Soft delete - mark as inactive
        listing.is_active = False
        listing.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(f"Casual listing deleted: {listing_id} by user {current_user.id}")
        
        return {"message": "Listing deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting listing {listing_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete listing"
        )

@router.get("/categories/list")
async def get_listing_categories():
    """Get available listing categories"""
    categories = [
        "Electronics",
        "Clothing & Accessories", 
        "Home & Garden",
        "Books & Media",
        "Sports & Recreation",
        "Vehicles",
        "Furniture",
        "Toys & Games",
        "Health & Beauty",
        "Tools & Equipment",
        "Art & Crafts",
        "Musical Instruments",
        "Food & Beverages",
        "Other"
    ]
    
    return {"categories": categories}

@router.get("/conditions/list")
async def get_item_conditions():
    """Get available item conditions"""
    conditions = [
        "New",
        "Like New", 
        "Very Good",
        "Good",
        "Fair",
        "Poor",
        "For Parts"
    ]
    
    return {"conditions": conditions}