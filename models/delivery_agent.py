import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, DECIMAL, Integer, JSON
from sqlalchemy.orm import relationship
from database.base import Base

class DeliveryAgent(Base):
    __tablename__ = "delivery_agents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    vehicle_type = Column(String(50), nullable=True)  # 'bike', 'scooter', 'car', 'van'
    license_number = Column(String(100), nullable=True)
    is_verified = Column(Boolean, default=False)
    availability_schedule = Column(JSON, nullable=True)  # Weekly schedule
    current_status = Column(String(20), default='offline')  # 'online', 'offline', 'busy'
    current_location = Column(String(255), nullable=True)  # GPS coordinates as string
    rating = Column(DECIMAL(3,2), default=5.0)
    total_deliveries = Column(Integer, default=0)
    earnings_this_month = Column(DECIMAL(10,2), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="delivery_agent")
    assignments = relationship("DeliveryAssignment", back_populates="agent")


class DeliveryAssignment(Base):
    __tablename__ = "delivery_assignments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    order_id = Column(String, nullable=False)  # Will reference orders table
    agent_id = Column(String, ForeignKey("delivery_agents.id"), nullable=False)
    status = Column(String(20), default='assigned')  # 'assigned', 'picked_up', 'delivered', 'cancelled'
    pickup_location = Column(String(255), nullable=True)
    delivery_location = Column(String(255), nullable=True)
    estimated_distance = Column(DECIMAL(5,2), nullable=True)  # in km
    delivery_fee = Column(DECIMAL(10,2), nullable=True)
    agent_earnings = Column(DECIMAL(10,2), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    picked_up_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    agent = relationship("DeliveryAgent", back_populates="assignments")