from sqlalchemy import Column, String, DateTime, Text, Boolean, ForeignKey, Integer, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.connection import Base
import enum
import uuid

class ConversationType(enum.Enum):
    DIRECT_MESSAGE = "direct_message"
    GROUP_CHAT = "group_chat"
    CUSTOMER_SUPPORT = "customer_support"
    SHOP_CUSTOMER = "shop_customer"
    BUSINESS_CHAT = "business_chat"

class MessageStatus(enum.Enum):
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    type = Column(Enum(ConversationType), nullable=False)
    title = Column(String(200), nullable=True)

    # Creator and basic info
    created_by = Column(String, ForeignKey("users.id"), nullable=False)

    # Group chat specific fields
    group_name = Column(String(200), nullable=True)
    group_description = Column(Text, nullable=True)
    group_avatar = Column(String(500), nullable=True)
    is_group_admin_only_messages = Column(Boolean, default=False)

    # Business context (optional)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=True)
    order_id = Column(String, ForeignKey("orders.id"), nullable=True)
    product_id = Column(String, ForeignKey("products.id"), nullable=True)

    # Status tracking
    is_active = Column(Boolean, default=True)
    is_escalated = Column(Boolean, default=False)
    priority = Column(String(20), default="normal")  # low, normal, high, urgent

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_message_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    creator = relationship("User", foreign_keys=[created_by], backref="created_conversations")
    shop = relationship("Shop", foreign_keys=[shop_id], backref="shop_conversations")
    order = relationship("Order", foreign_keys=[order_id], backref="conversation")
    product = relationship("Product", foreign_keys=[product_id], backref="conversations")
    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")
    participants = relationship("ConversationParticipant", back_populates="conversation")

class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    sender_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Message content
    content = Column(Text, nullable=False)
    message_type = Column(String(50), default="text")  # text, image, file, system, bot_response

    # File attachments
    attachment_url = Column(String(500), nullable=True)
    attachment_type = Column(String(50), nullable=True)  # image, document, audio, video
    attachment_name = Column(String(200), nullable=True)
    attachment_size = Column(Integer, nullable=True)

    # Status and metadata
    status = Column(Enum(MessageStatus), default=MessageStatus.SENT)
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    reply_to_id = Column(String, ForeignKey("messages.id"), nullable=True)

    # AI/Bot related
    is_bot_message = Column(Boolean, default=False)
    bot_confidence = Column(Integer, nullable=True)  # 0-100
    requires_human_escalation = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id], backref="sent_messages")
    reply_to = relationship("Message", remote_side=[id], backref="replies")

class MessageReaction(Base):
    __tablename__ = "message_reactions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    message_id = Column(String, ForeignKey("messages.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    reaction_type = Column(String(50), nullable=False)  # like, love, laugh, angry, sad, etc.

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message = relationship("Message", backref="reactions")
    user = relationship("User", backref="message_reactions")

class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    # Participant status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # For group chats
    last_read_message_id = Column(String, ForeignKey("messages.id"), nullable=True)
    unread_count = Column(Integer, default=0)

    # Group permissions
    can_send_messages = Column(Boolean, default=True)
    can_add_members = Column(Boolean, default=False)
    can_edit_group = Column(Boolean, default=False)

    # Notification settings
    notifications_enabled = Column(Boolean, default=True)
    muted_until = Column(DateTime(timezone=True), nullable=True)

    # Custom settings
    nickname = Column(String(100), nullable=True)  # Custom name in group
    pinned_message_id = Column(String, ForeignKey("messages.id"), nullable=True)

    # Timestamps
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="participants")
    user = relationship("User", backref="conversation_participations")
    last_read_message = relationship("Message", foreign_keys=[last_read_message_id])
    pinned_message = relationship("Message", foreign_keys=[pinned_message_id])

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)

    # Ticket metadata
    ticket_number = Column(String(50), unique=True, nullable=False)
    category = Column(String(100), nullable=False)  # account, order, payment, technical, etc.
    priority = Column(String(20), default="normal")
    status = Column(String(50), default="open")  # open, pending, resolved, closed

    # Assignment
    assigned_to = Column(String, ForeignKey("users.id"), nullable=True)
    department = Column(String(100), nullable=True)

    # Resolution
    resolution_notes = Column(Text, nullable=True)
    satisfaction_rating = Column(Integer, nullable=True)  # 1-5

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("Conversation", backref="support_ticket")
    assigned_agent = relationship("User", foreign_keys=[assigned_to], backref="assigned_tickets")