import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base

class Shop(Base):
    __tablename__ = "shops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=False)
    logo_url = Column(String, nullable=True)
    banner_url = Column(String, nullable=True)
    contact_email = Column(String, nullable=False)
    contact_phone = Column(String, nullable=False)
    address = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    total_sales = Column(Numeric(10, 2), default=0.00)
    total_orders = Column(Integer, default=0)
    rating_average = Column(Numeric(3, 2), default=0.00)
    rating_count = Column(Integer, default=0)

    # Relationships
    owner = relationship("User", back_populates="shop")
    products = relationship("Product", back_populates="shop")
    orders = relationship("Order", back_populates="shop") 