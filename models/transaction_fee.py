import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, ForeignKey, DECIMAL, Integer
from sqlalchemy.orm import relationship
from database.base import Base

class TransactionFee(Base):
    __tablename__ = "transaction_fees"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    order_id = Column(String, nullable=True)  # Will reference orders table when available
    listing_id = Column(String, nullable=True)  # Can reference casual_listings or shop products
    fee_type = Column(String(50), nullable=False)  # 'casual_seller', 'shop_owner', 'delivery'
    fee_percentage = Column(DECIMAL(5,2), nullable=False)  # e.g., 5.00 for 5%
    fee_amount = Column(DECIMAL(10,2), nullable=False)  # Actual fee amount in dollars
    platform_revenue = Column(DECIMAL(10,2), nullable=False)  # Revenue for platform
    transaction_amount = Column(DECIMAL(10,2), nullable=False)  # Original transaction amount
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User", back_populates="transaction_fees")


class UserMetrics(Base):
    __tablename__ = "user_metrics"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    total_purchases = Column(Integer, default=0)
    monthly_purchases = Column(Integer, default=0)
    total_spent = Column(DECIMAL(10,2), default=0)
    monthly_spent = Column(DECIMAL(10,2), default=0)
    total_listings = Column(Integer, default=0)
    total_sales = Column(Integer, default=0)
    page_views = Column(Integer, default=0)
    time_spent_minutes = Column(Integer, default=0)
    last_upgrade_prompt = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="metrics")