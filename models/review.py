import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from database.base import Base

class Review(Base):
    __tablename__ = "reviews"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    product_id = Column(String, ForeignKey("products.id"), nullable=True)  # Optional - can be shop review or product review
    rating = Column(Float, nullable=False)  # 1.0 to 5.0
    title = Column(String, nullable=True)
    comment = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False)
    helpful_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shop = relationship("Shop", back_populates="reviews")
    user = relationship("User", back_populates="reviews")
    product = relationship("Product", back_populates="reviews")
