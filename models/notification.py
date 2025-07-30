import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Enum, Integer
from sqlalchemy.orm import relationship
from database.base import Base
import enum

class NotificationType(enum.Enum):
    ORDER = "order"
    PAYMENT = "payment"
    SYSTEM = "system"
    MARKETING = "marketing"
    SHOP = "shop"
    PRODUCT = "product"
    CUSTOMER = "customer"
    SECURITY = "security"

class NotificationPriority(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"

class NotificationStatus(enum.Enum):
    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"
    DELETED = "deleted"

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Notification content
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(Enum(NotificationType), nullable=False, index=True)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.MEDIUM, index=True)
    status = Column(Enum(NotificationStatus), default=NotificationStatus.UNREAD, index=True)
    
    # Metadata
    action_url = Column(String(500), nullable=True)  # URL to navigate when clicked
    action_label = Column(String(100), nullable=True)  # Button label
    icon = Column(String(50), nullable=True)  # Icon name
    image_url = Column(String(500), nullable=True)  # Optional image
    
    # Related entities
    related_id = Column(String, nullable=True, index=True)  # ID of related entity (order, product, etc.)
    related_type = Column(String(50), nullable=True)  # Type of related entity
    
    # Scheduling
    scheduled_at = Column(DateTime, nullable=True)  # For scheduled notifications
    expires_at = Column(DateTime, nullable=True)  # When notification expires
    
    # Tracking
    is_read = Column(Boolean, default=False, index=True)
    is_pushed = Column(Boolean, default=False)  # Whether push notification was sent
    read_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="notifications")

class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Email preferences
    email_orders = Column(Boolean, default=True)
    email_payments = Column(Boolean, default=True)
    email_marketing = Column(Boolean, default=False)
    email_system = Column(Boolean, default=True)
    email_security = Column(Boolean, default=True)
    
    # Push notification preferences
    push_orders = Column(Boolean, default=True)
    push_payments = Column(Boolean, default=True)
    push_marketing = Column(Boolean, default=False)
    push_system = Column(Boolean, default=True)
    push_security = Column(Boolean, default=True)
    
    # SMS preferences
    sms_orders = Column(Boolean, default=False)
    sms_payments = Column(Boolean, default=True)
    sms_security = Column(Boolean, default=True)
    
    # General preferences
    quiet_hours_start = Column(String(5), default="22:00")  # Format: HH:MM
    quiet_hours_end = Column(String(5), default="08:00")
    timezone = Column(String(50), default="UTC")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="notification_preferences")

class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    type = Column(Enum(NotificationType), nullable=False)
    
    # Template content
    title_template = Column(String(255), nullable=False)
    message_template = Column(Text, nullable=False)
    action_label_template = Column(String(100), nullable=True)
    icon = Column(String(50), nullable=True)
    
    # Settings
    is_active = Column(Boolean, default=True)
    priority = Column(Enum(NotificationPriority), default=NotificationPriority.MEDIUM)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class NotificationBatch(Base):
    __tablename__ = "notification_batches"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Targeting
    target_user_ids = Column(Text, nullable=True)  # JSON array of user IDs
    target_roles = Column(String(255), nullable=True)  # Comma-separated roles
    target_criteria = Column(Text, nullable=True)  # JSON criteria
    
    # Content
    template_id = Column(String, ForeignKey("notification_templates.id"), nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Status
    status = Column(String(20), default="draft")  # draft, scheduled, sending, sent, failed
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    
    # Scheduling
    scheduled_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    template = relationship("NotificationTemplate")