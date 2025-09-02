import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, String, DateTime, ForeignKey, DECIMAL, JSON, Text
from sqlalchemy.orm import relationship
from database.base import Base

class DeliveryTracking(Base):
    __tablename__ = "delivery_tracking"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=False, index=True)
    
    # Partner delivery information
    partner_delivery_id = Column(String(255), nullable=True, index=True)
    partner_tracking_number = Column(String(100), nullable=True, unique=True, index=True)
    
    # Status and tracking
    status = Column(String(50), nullable=False, default='requested', index=True)
    # Possible statuses: requested, accepted, pickup_scheduled, picked_up, in_transit, 
    # out_for_delivery, delivered, failed, cancelled, exception
    
    # Location information
    pickup_location = Column(JSON, nullable=True)  # {address, lat, lng, contact_name, contact_phone}
    delivery_location = Column(JSON, nullable=True)  # {address, lat, lng, contact_name, contact_phone}
    current_location = Column(JSON, nullable=True)  # {lat, lng, timestamp}
    
    # Delivery details
    estimated_delivery_fee = Column(DECIMAL(10,2), nullable=True)
    actual_delivery_fee = Column(DECIMAL(10,2), nullable=True)
    estimated_delivery_time = Column(DateTime, nullable=True)
    
    # Driver information (populated from partner webhooks)
    driver_info = Column(JSON, nullable=True)  # {name, phone, vehicle, photo}
    
    # Status history and tracking
    status_history = Column(JSON, nullable=True)  # Array of status updates with timestamps
    
    # Exception handling
    exception_reason = Column(String(255), nullable=True)
    exception_details = Column(Text, nullable=True)
    cancellation_reason = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    pickup_scheduled_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="delivery_tracking")