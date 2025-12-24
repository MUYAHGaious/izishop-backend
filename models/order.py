import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Text, Integer, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from database.base import Base
import enum

class OrderStatus(enum.Enum):
    # Pre-fulfillment stages
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PAYMENT_PROCESSING = "payment_processing"
    PAYMENT_CONFIRMED = "payment_confirmed"

    # Fulfillment stages
    PROCESSING = "processing"
    PICKING = "picking"
    PACKED = "packed"
    READY_FOR_PICKUP = "ready_for_pickup"

    # Shipping stages
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERY_ATTEMPTED = "delivery_attempted"

    # Completion stages
    DELIVERED = "delivered"
    COMPLETED = "completed"

    # Exception stages
    CANCELLED = "cancelled"
    RETURNED = "returned"
    REFUNDED = "refunded"
    EXCEPTION = "exception"

class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    customer_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=False, index=True)
    total_amount = Column(Numeric(10, 2), nullable=False)
    delivery_cost = Column(Numeric(10, 2), default=0, nullable=False)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, index=True)
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, index=True)
    payment_method = Column(String(50), nullable=True)  # e.g., 'mtn_momo', 'orange_money'
    payment_reference = Column(String(100), nullable=True)  # Transaction ID from payment gateway
    shipping_address = Column(Text, nullable=True)
    tracking_number = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    estimated_delivery_date = Column(DateTime, nullable=True)
    carrier = Column(String(100), nullable=True)
    delivery_instructions = Column(Text, nullable=True)
    status_updated_at = Column(DateTime, nullable=True)

    # Enhanced status tracking timestamps
    confirmed_at = Column(DateTime, nullable=True)
    payment_confirmed_at = Column(DateTime, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    packed_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)
    shipped_at = Column(DateTime, nullable=True)
    out_for_delivery_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Dynamic delivery estimate (updates based on carrier info)
    current_estimated_delivery = Column(DateTime, nullable=True)
    delivery_window_start = Column(DateTime, nullable=True)
    delivery_window_end = Column(DateTime, nullable=True)

    # Cancellation tracking
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(String(100), nullable=True)
    can_be_cancelled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # customer = relationship("User", back_populates="orders_as_customer")
    # shop = relationship("Shop", back_populates="orders")
    # items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    delivery_tracking = relationship("DeliveryTracking", back_populates="order", uselist=False)
    status_history = relationship("OrderStatusHistory", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=True, index=True)  # Nullable for casual listings
    casual_listing_id = Column(String, ForeignKey("casual_listings.id"), nullable=True, index=True)  # For casual marketplace
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # order = relationship("Order", back_populates="items")
    # product = relationship("Product", back_populates="order_items")


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    changed_by = Column(String, ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, index=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="status_history")
    # changed_by_user = relationship("User", foreign_keys=[changed_by])