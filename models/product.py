import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Integer, Text, JSON
from sqlalchemy.orm import relationship
from database.base import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    seller_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False)
    stock_quantity = Column(Integer, default=0)
    category = Column(String(100), nullable=True, index=True)  # Product category
    is_active = Column(Boolean, default=True)
    image_urls = Column(JSON, nullable=True)  # Store array of image URLs
    video_urls = Column(JSON, nullable=True)  # Store array of video URLs
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # seller = relationship("User", back_populates="products_as_seller")
    # order_items = relationship("OrderItem", back_populates="product")


class ProductReview(Base):
    __tablename__ = "product_reviews"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    title = Column(String, nullable=True)
    content = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    helpful_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # product = relationship("Product", back_populates="reviews")
    # user = relationship("User", back_populates="product_reviews")

    def __repr__(self):
        return f"<ProductReview(id={self.id}, product_id={self.product_id}, user_id={self.user_id}, rating={self.rating})>" 