import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base
import enum

class TransactionType(str, enum.Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
    ESCROW_HOLD = "ESCROW_HOLD"
    ESCROW_RELEASE = "ESCROW_RELEASE"

class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    available_balance = Column(Numeric(10, 2), default=0.00)
    pending_balance = Column(Numeric(10, 2), default=0.00)
    total_earned = Column(Numeric(10, 2), default=0.00)
    total_withdrawn = Column(Numeric(10, 2), default=0.00)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="wallet")
    transactions = relationship("WalletTransaction", back_populates="wallet")

class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)
    transaction_type = Column(Enum(TransactionType), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=False)
    reference_id = Column(String, nullable=False)
    balance_before = Column(Numeric(10, 2), nullable=False)
    balance_after = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    wallet = relationship("Wallet", back_populates="transactions") 