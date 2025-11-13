"""
Casual Listing Models for Marketplace
Industry-standard implementation for casual seller marketplace
"""

from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, Text, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base
import uuid


class CasualListing(Base):
    """
    Casual Listing model for marketplace items sold by casual sellers and customers
    Industry-standard marketplace listing with full features
    """
    __tablename__ = "casual_listings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Basic listing information
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=False)
    price = Column(Float, nullable=False, index=True)
    original_price = Column(Float, nullable=True)  # For discounted items
    condition = Column(String(50), nullable=False, index=True)  # New, Like New, Good, Fair, Poor
    category = Column(String(100), nullable=False, index=True)
    subcategory = Column(String(100), nullable=True)

    # Location and logistics
    location = Column(String(200), nullable=False)
    city = Column(String(100), nullable=True, index=True)
    region = Column(String(100), nullable=True, index=True)
    is_negotiable = Column(Boolean, default=False)
    is_delivery_available = Column(Boolean, default=False)
    delivery_fee = Column(Float, nullable=True)

    # Seller information
    seller_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    seller_type = Column(String(50), nullable=False, default="casual_seller")  # casual_seller, customer

    # Media and presentation
    image_urls = Column(JSON, nullable=True)  # Array of image URLs
    tags = Column(JSON, nullable=True)  # Array of tags for search

    # Listing status and metrics
    status = Column(String(50), nullable=False, default="active", index=True)  # active, sold, expired, suspended
    views_count = Column(Integer, default=0)
    favorites_count = Column(Integer, default=0)
    inquiries_count = Column(Integer, default=0)

    # Marketplace features
    is_featured = Column(Boolean, default=False)
    is_urgent = Column(Boolean, default=False)
    boost_expires_at = Column(DateTime, nullable=True)

    # Business logic
    expires_at = Column(DateTime, nullable=True)  # Auto-expire listings
    sold_at = Column(DateTime, nullable=True)
    sold_price = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    seller = relationship("User", foreign_keys=[seller_id], back_populates="casual_listings")
    inquiries = relationship("CasualListingInquiry", back_populates="listing", cascade="all, delete-orphan")
    favorites = relationship("CasualListingFavorite", back_populates="listing", cascade="all, delete-orphan")

    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "price": self.price,
            "original_price": self.original_price,
            "condition": self.condition,
            "category": self.category,
            "subcategory": self.subcategory,
            "location": self.location,
            "city": self.city,
            "region": self.region,
            "is_negotiable": self.is_negotiable,
            "is_delivery_available": self.is_delivery_available,
            "delivery_fee": self.delivery_fee,
            "seller_id": self.seller_id,
            "seller_type": self.seller_type,
            "image_urls": self.image_urls or [],
            "tags": self.tags or [],
            "status": self.status,
            "views_count": self.views_count,
            "favorites_count": self.favorites_count,
            "inquiries_count": self.inquiries_count,
            "is_featured": self.is_featured,
            "is_urgent": self.is_urgent,
            "boost_expires_at": self.boost_expires_at.isoformat() if self.boost_expires_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "sold_at": self.sold_at.isoformat() if self.sold_at else None,
            "sold_price": self.sold_price,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Add stock fields for compatibility with product detail page
            # Casual listings are one-of-a-kind items, so stock is always 1 if active, 0 if sold
            "stock": 1 if self.status == "active" else 0,
            "stock_quantity": 1 if self.status == "active" else 0
        }


class CasualListingInquiry(Base):
    """
    Inquiries from potential buyers about casual listings
    """
    __tablename__ = "casual_listing_inquiries"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    listing_id = Column(String, ForeignKey("casual_listings.id"), nullable=False, index=True)
    inquirer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    message = Column(Text, nullable=False)
    offered_price = Column(Float, nullable=True)  # If making an offer
    contact_phone = Column(String(20), nullable=True)
    contact_email = Column(String(100), nullable=True)

    status = Column(String(50), nullable=False, default="pending")  # pending, replied, accepted, declined
    seller_reply = Column(Text, nullable=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    listing = relationship("CasualListing", foreign_keys=[listing_id], back_populates="inquiries")
    inquirer = relationship("User", foreign_keys=[inquirer_id])

    def to_dict(self):
        return {
            "id": self.id,
            "listing_id": self.listing_id,
            "inquirer_id": self.inquirer_id,
            "message": self.message,
            "offered_price": self.offered_price,
            "contact_phone": self.contact_phone,
            "contact_email": self.contact_email,
            "status": self.status,
            "seller_reply": self.seller_reply,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


class CasualListingFavorite(Base):
    """
    User favorites for casual listings (wishlist)
    """
    __tablename__ = "casual_listing_favorites"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    listing_id = Column(String, ForeignKey("casual_listings.id"), nullable=False, index=True)

    created_at = Column(DateTime, default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    listing = relationship("CasualListing", foreign_keys=[listing_id], back_populates="favorites")

    # Unique constraint to prevent duplicate favorites
    __table_args__ = (
        Index('idx_unique_user_listing_favorite', 'user_id', 'listing_id', unique=True),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "listing_id": self.listing_id,
            "created_at": self.created_at.isoformat()
        }