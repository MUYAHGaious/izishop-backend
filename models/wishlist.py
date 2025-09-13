"""
Wishlist Model
Manages user wishlist items and preferences
"""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone
import uuid

from database.connection import Base


class Wishlist(Base):
    __tablename__ = "wishlist"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    # Timestamps
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Additional metadata for wishlist item
    item_metadata = Column(Text, nullable=True)  # JSON string for additional data

    # Optional priority or notes
    priority = Column(String, default="normal", nullable=True)  # low, normal, high
    notes = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="wishlist_items")
    product = relationship("Product", back_populates="wishlist_items")

    def __repr__(self):
        return f"<Wishlist(id={self.id}, user_id={self.user_id}, product_id={self.product_id})>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "product_id": self.product_id,
            "added_at": self.added_at.isoformat() if self.added_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "item_metadata": self.item_metadata,
            "priority": self.priority,
            "notes": self.notes,
            "product": self.product.to_dict() if self.product else None
        }


class WishlistPreference(Base):
    """User preferences for wishlist notifications and behaviors"""
    __tablename__ = "wishlist_preferences"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Notification preferences
    price_drop_notifications = Column(Boolean, default=True)
    stock_availability_notifications = Column(Boolean, default=True)
    weekly_summary_notifications = Column(Boolean, default=False)

    # Wishlist behaviors
    auto_remove_unavailable = Column(Boolean, default=False)
    max_wishlist_size = Column(String, default="unlimited")  # "unlimited" or number

    # Privacy settings
    wishlist_public = Column(Boolean, default=False)
    allow_wishlist_sharing = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("User", back_populates="wishlist_preferences")

    def __repr__(self):
        return f"<WishlistPreference(user_id={self.user_id})>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "price_drop_notifications": self.price_drop_notifications,
            "stock_availability_notifications": self.stock_availability_notifications,
            "weekly_summary_notifications": self.weekly_summary_notifications,
            "auto_remove_unavailable": self.auto_remove_unavailable,
            "max_wishlist_size": self.max_wishlist_size,
            "wishlist_public": self.wishlist_public,
            "allow_wishlist_sharing": self.allow_wishlist_sharing,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }