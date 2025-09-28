from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey, Integer, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.connection import Base
import enum
import uuid

class ContactStatus(enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    DECLINED = "declined"

class Contact(Base):
    __tablename__ = "contacts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Who initiated the contact request
    requester_id = Column(String, ForeignKey("users.id"), nullable=False)
    # Who received the contact request
    addressee_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Contact status
    status = Column(Enum(ContactStatus), default=ContactStatus.PENDING)

    # Custom contact info
    nickname = Column(String(100), nullable=True)  # Custom name for contact
    notes = Column(Text, nullable=True)  # Private notes about contact

    # Contact settings
    is_favorite = Column(Boolean, default=False)
    notifications_enabled = Column(Boolean, default=True)
    is_blocked = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    blocked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    requester = relationship("User", foreign_keys=[requester_id], backref="sent_contact_requests")
    addressee = relationship("User", foreign_keys=[addressee_id], backref="received_contact_requests")

class UserStatus(Base):
    __tablename__ = "user_status"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)

    # Online status
    is_online = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now())

    # Status message
    status_message = Column(String(200), nullable=True)
    status_emoji = Column(String(10), nullable=True)

    # Privacy settings
    show_online_status = Column(Boolean, default=True)
    show_last_seen = Column(Boolean, default=True)
    who_can_message = Column(String(20), default="everyone")  # everyone, contacts, nobody
    who_can_add_to_groups = Column(String(20), default="everyone")

    # Activity
    current_conversation_id = Column(String, ForeignKey("conversations.id"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="status")
    current_conversation = relationship("Conversation", foreign_keys=[current_conversation_id])

class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    blocker_id = Column(String, ForeignKey("users.id"), nullable=False)
    blocked_id = Column(String, ForeignKey("users.id"), nullable=False)

    reason = Column(String(200), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    blocker = relationship("User", foreign_keys=[blocker_id], backref="blocked_users")
    blocked = relationship("User", foreign_keys=[blocked_id], backref="blocked_by_users")

class UserSearchHistory(Base):
    __tablename__ = "user_search_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    search_query = Column(String(200), nullable=False)
    search_type = Column(String(50), default="user_search")  # user_search, group_search, message_search

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="search_history")