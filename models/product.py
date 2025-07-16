import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Integer, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base
import enum

class ProductCondition(str, enum.Enum):
    NEW = "NEW"
    USED_LIKE_NEW = "USED_LIKE_NEW"
    USED_GOOD = "USED_GOOD"
    USED_ACCEPTABLE = "USED_ACCEPTABLE"

class ProductStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SOLD_OUT = "SOLD_OUT"
    DISCONTINUED = "DISCONTINUED"

class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seller_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=False)
    condition = Column(Enum(ProductCondition), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="XAF", nullable=False)
    quantity_available = Column(Integer, default=1)
    quantity_sold = Column(Integer, default=0)
    is_unlimited_stock = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)
    status = Column(Enum(ProductStatus), default=ProductStatus.DRAFT, nullable=False)
    slug = Column(String, unique=True, nullable=False)
    tags = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    seller = relationship("User", back_populates="products_as_seller")
    shop = relationship("Shop", back_populates="products")
    category = relationship("Category", back_populates="products")
    images = relationship("ProductImage", back_populates="product")
    orders = relationship("OrderItem", back_populates="product")

class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    image_url = Column(String, nullable=False)
    alt_text = Column(String, nullable=True)
    sort_order = Column(Integer, default=0)
    is_primary = Column(Boolean, default=False)

    # Relationships
    product = relationship("Product", back_populates="images") 