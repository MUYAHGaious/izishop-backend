import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from database.base import Base
import enum

class UserRole(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SHOP_OWNER = "SHOP_OWNER"
    CASUAL_SELLER = "CASUAL_SELLER"
    DELIVERY_AGENT = "DELIVERY_AGENT"
    ADMIN = "ADMIN"

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    verification_token = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    profile_image_url = Column(String, nullable=True)

    # Relationships - Simplified for microservice
    # These will be handled through service communication
    # shop = relationship("Shop", uselist=False, back_populates="owner")
    # notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    # notification_preferences = relationship("NotificationPreference", uselist=False, back_populates="user", cascade="all, delete-orphan")
    # orders_as_customer = relationship("Order", back_populates="customer", foreign_keys="Order.customer_id")
    # products_as_seller = relationship("Product", back_populates="seller", foreign_keys="Product.seller_id")
    # deliveries_assigned = relationship("Delivery", back_populates="delivery_agent", foreign_keys="Delivery.delivery_agent_id")
    # wallet = relationship("Wallet", uselist=False, back_populates="user")
    # ratings = relationship("Rating", back_populates="user")

    def __repr__(self):
        return f"<User(id='{self.id}', email='{self.email}', role='{self.role}')>"

    @property
    def full_name(self) -> str:
        """Get the user's full name."""
        return f"{self.first_name} {self.last_name}"

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin."""
        return self.role == UserRole.ADMIN

    @property
    def is_shop_owner(self) -> bool:
        """Check if user is a shop owner."""
        return self.role == UserRole.SHOP_OWNER

    @property
    def is_customer(self) -> bool:
        """Check if user is a customer."""
        return self.role == UserRole.CUSTOMER 