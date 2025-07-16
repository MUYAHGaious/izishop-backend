import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Integer, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base
import enum

class OrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    READY_FOR_DELIVERY = "READY_FOR_DELIVERY"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    DISPUTED = "DISPUTED"

class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id"), nullable=True)
    order_number = Column(String, unique=True, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    platform_fee = Column(Numeric(10, 2), nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="XAF", nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    shipping_address = Column(Text, nullable=False)
    customer_phone = Column(String, nullable=False)
    customer_email = Column(String, nullable=False)
    special_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    payment_confirmed_at = Column(DateTime, nullable=True)
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    customer = relationship("User", back_populates="orders_as_customer")
    shop = relationship("Shop", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")
    payment = relationship("Payment", uselist=False, back_populates="order")
    delivery = relationship("Delivery", uselist=False, back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    product_name = Column(String, nullable=False)
    product_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="orders") 