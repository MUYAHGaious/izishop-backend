import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base
import enum

class DeliveryStatus(str, enum.Enum):
    PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT"
    ASSIGNED = "ASSIGNED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RETURNED = "RETURNED"

class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), unique=True, nullable=False)
    delivery_agent_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    pickup_address = Column(Text, nullable=False)
    delivery_address = Column(Text, nullable=False)
    estimated_delivery_date = Column(DateTime, nullable=False)
    actual_delivery_date = Column(DateTime, nullable=True)
    status = Column(Enum(DeliveryStatus), default=DeliveryStatus.PENDING_ASSIGNMENT, nullable=False)
    delivery_confirmation_code = Column(String, nullable=False)
    customer_confirmed = Column(Boolean, default=False)
    customer_confirmed_at = Column(DateTime, nullable=True)
    delivery_notes = Column(Text, nullable=True)
    delivery_photo_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    assigned_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="delivery")
    delivery_agent = relationship("User", back_populates="deliveries_assigned") 