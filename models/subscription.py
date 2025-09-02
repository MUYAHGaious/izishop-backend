import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from database.base import Base

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    plan_type = Column(String(50), nullable=False)  # 'shop_owner', 'casual_seller', 'delivery_agent'
    status = Column(String(20), nullable=False)  # 'active', 'cancelled', 'expired', 'trial'
    current_period_start = Column(DateTime, nullable=False)
    current_period_end = Column(DateTime, nullable=False)
    monthly_fee = Column(DECIMAL(10,2), nullable=False)
    trial_ends_at = Column(DateTime, nullable=True)
    tranzak_request_id = Column(String(255), nullable=True, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="subscription")