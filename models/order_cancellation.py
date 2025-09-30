import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Text, Enum
from sqlalchemy.orm import relationship
from database.base import Base
import enum

class CancellationReason(enum.Enum):
    """Order cancellation reasons"""
    CUSTOMER_REQUEST = "customer_request"
    PAYMENT_FAILED = "payment_failed"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"
    SHIPPING_ISSUES = "shipping_issues"
    DUPLICATE_ORDER = "duplicate_order"
    PRICING_ERROR = "pricing_error"
    CUSTOMER_CHANGED_MIND = "customer_changed_mind"
    WRONG_ITEM_ORDERED = "wrong_item_ordered"
    DELIVERY_ISSUES = "delivery_issues"
    OTHER = "other"

class RefundStatus(enum.Enum):
    """Refund processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class OrderCancellation(Base):
    """Model for tracking order cancellations following industry patterns"""
    __tablename__ = "order_cancellations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    cancelled_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Cancellation details
    reason = Column(Enum(CancellationReason), nullable=False)
    description = Column(Text, nullable=True)
    cancelled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Refund information
    refund_requested = Column(Boolean, default=True, nullable=False)
    refund_amount = Column(Numeric(10, 2), nullable=True)
    refund_status = Column(Enum(RefundStatus), default=RefundStatus.PENDING)
    refund_reference = Column(String(100), nullable=True)  # Payment gateway reference

    # Inventory management
    items_restocked = Column(Boolean, default=False, nullable=False)
    restock_completed_at = Column(DateTime, nullable=True)

    # System tracking
    processed_at = Column(DateTime, nullable=True)
    processing_notes = Column(Text, nullable=True)

    # Relationships
    # order = relationship("Order", back_populates="cancellations")
    # cancelled_by_user = relationship("User")