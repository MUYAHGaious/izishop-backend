import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, DECIMAL, Text, Integer, JSON
from sqlalchemy.orm import relationship
from database.base import Base

class CasualListing(Base):
    __tablename__ = "casual_listings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    seller_id = Column(String, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(DECIMAL(10,2), nullable=False)
    category = Column(String(100), nullable=True)
    condition = Column(String(50), nullable=True)  # 'new', 'used', 'refurbished', etc.
    images = Column(JSON, nullable=True)  # Array of image URLs
    location = Column(String(255), nullable=True)
    is_negotiable = Column(Boolean, default=False)
    tags = Column(JSON, nullable=True)  # Array of tags
    is_active = Column(Boolean, default=True)
    is_promoted = Column(Boolean, default=False)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    seller = relationship("User", back_populates="casual_listings")