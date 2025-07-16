import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base
import enum

class PaymentMethod(str, enum.Enum):
    MTN_MOMO = "MTN_MOMO"
    ORANGE_MONEY = "ORANGE_MONEY"
    VISA = "VISA"

class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False)
    tranzak_transaction_id = Column(String, unique=True, nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="XAF", nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=False)
    customer_phone = Column(String, nullable=True)
    payment_auth_url = Column(String, nullable=True)
    return_url = Column(String, nullable=True)
    callback_url = Column(String, nullable=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    tranzak_status = Column(String, nullable=True)
    escrow_amount = Column(Numeric(10, 2), nullable=False)
    platform_fee = Column(Numeric(10, 2), nullable=False)
    seller_payout_amount = Column(Numeric(10, 2), nullable=False)
    escrow_released_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="payment") 