"""
Audit Log models for comprehensive system tracking
Implements security audit trail like AWS CloudTrail
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, UUID, JSON, Index, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey
from database.base import Base
from enum import Enum
import uuid
from datetime import datetime, timezone

class AuditAction(str, Enum):
    """Types of auditable actions"""
    # Authentication
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILED = "auth.login.failed"
    LOGOUT = "auth.logout"
    TOKEN_REFRESH = "auth.token.refresh"
    PASSWORD_CHANGE = "auth.password.change"
    
    # Role Management
    ROLE_UPGRADE = "role.upgrade"
    ROLE_DOWNGRADE = "role.downgrade"
    ROLE_ASSIGNMENT = "role.assignment"
    PERMISSION_GRANTED = "permission.granted"
    PERMISSION_REVOKED = "permission.revoked"
    
    # User Management
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_SUSPENDED = "user.suspended"
    USER_ACTIVATED = "user.activated"
    
    # Shop Management
    SHOP_CREATED = "shop.created"
    SHOP_UPDATED = "shop.updated"
    SHOP_DELETED = "shop.deleted"
    SHOP_APPROVED = "shop.approved"
    SHOP_REJECTED = "shop.rejected"
    
    # Product Management
    PRODUCT_CREATED = "product.created"
    PRODUCT_UPDATED = "product.updated"
    PRODUCT_DELETED = "product.deleted"
    PRODUCT_PUBLISHED = "product.published"
    PRODUCT_UNPUBLISHED = "product.unpublished"
    
    # Order Management
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_CANCELLED = "order.cancelled"
    ORDER_FULFILLED = "order.fulfilled"
    
    # Payment Management
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_REFUNDED = "payment.refunded"
    
    # System Administration
    SYSTEM_CONFIG_CHANGED = "system.config.changed"
    BULK_ACTION_EXECUTED = "system.bulk.action"
    DATA_EXPORT = "data.export"
    DATA_IMPORT = "data.import"
    
    # Security Events
    SECURITY_BREACH_DETECTED = "security.breach.detected"
    SUSPICIOUS_ACTIVITY = "security.suspicious.activity"
    ACCESS_DENIED = "security.access.denied"
    RATE_LIMIT_EXCEEDED = "security.rate_limit.exceeded"

class ResourceType(str, Enum):
    """Types of resources that can be audited"""
    USER = "user"
    SHOP = "shop"
    PRODUCT = "product"
    ORDER = "order"
    PAYMENT = "payment"
    NOTIFICATION = "notification"
    CATEGORY = "category"
    RATING = "rating"
    ANALYTICS = "analytics"
    SYSTEM = "system"

class AuditLog(Base):
    """Comprehensive audit log model"""
    __tablename__ = "audit_logs"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Actor (who performed the action)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_type = Column(String(50), default="user")  # user, system, api, cron
    actor_name = Column(String(255), nullable=True)  # For display purposes
    
    # Action details
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=True)
    resource_name = Column(String(255), nullable=True)
    
    # Change tracking
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    changes_summary = Column(Text, nullable=True)
    
    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(255), nullable=True)
    request_id = Column(String(255), nullable=True)
    request_method = Column(String(10), nullable=True)
    request_path = Column(String(500), nullable=True)
    
    # Result and metadata
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Additional context
    additional_data = Column(JSON, default={})
    tags = Column(String(500), nullable=True)  # Comma-separated tags for filtering
    
    # Timestamp
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    
    # Indexes for performance
    __table_args__ = (
        Index('ix_audit_user_timestamp', 'user_id', 'timestamp'),
        Index('ix_audit_action_timestamp', 'action', 'timestamp'),
        Index('ix_audit_resource_timestamp', 'resource_type', 'resource_id', 'timestamp'),
        Index('ix_audit_success_timestamp', 'success', 'timestamp'),
        Index('ix_audit_ip_timestamp', 'ip_address', 'timestamp'),
        Index('ix_audit_session_timestamp', 'session_id', 'timestamp'),
        Index('ix_audit_tags', 'tags'),
    )
    
    def to_dict(self):
        """Convert audit log to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "actor_type": self.actor_type,
            "actor_name": self.actor_name,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "changes_summary": self.changes_summary,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "user_agent": self.user_agent,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "request_method": self.request_method,
            "request_path": self.request_path,
            "success": self.success,
            "error_message": self.error_message,
            "error_code": self.error_code,
            "duration_ms": self.duration_ms,
            "additional_data": self.additional_data,
            "tags": self.tags,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
    
    def add_tag(self, tag: str):
        """Add a tag to the audit log"""
        if not self.tags:
            self.tags = tag
        else:
            tags = set(self.tags.split(','))
            tags.add(tag.strip())
            self.tags = ','.join(sorted(tags))
    
    def has_tag(self, tag: str) -> bool:
        """Check if audit log has a specific tag"""
        if not self.tags:
            return False
        return tag in self.tags.split(',')

class RoleChangeEvent(Base):
    """Specific tracking for role changes"""
    __tablename__ = "role_change_events"
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Role change details
    old_role = Column(String(50), nullable=False)
    new_role = Column(String(50), nullable=False)
    
    # Authorization context
    triggered_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    trigger_source = Column(String(100), nullable=False)  # user_request, admin_action, system, api
    approval_required = Column(Boolean, default=False)
    approved_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    
    # Business context
    reason = Column(Text, nullable=True)
    business_justification = Column(Text, nullable=True)
    
    # Request context
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(Text, nullable=True)
    session_id = Column(String(255), nullable=True)
    
    # Status and result
    status = Column(String(20), default="completed")  # pending, completed, failed, rolled_back
    error_message = Column(Text, nullable=True)
    rollback_reason = Column(Text, nullable=True)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rolled_back_by = Column(PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    
    # Additional metadata
    additional_data = Column(JSON, default={})
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    triggered_by_user = relationship("User", foreign_keys=[triggered_by])
    approved_by_user = relationship("User", foreign_keys=[approved_by])
    rolled_back_by_user = relationship("User", foreign_keys=[rolled_back_by])
    
    # Indexes
    __table_args__ = (
        Index('ix_role_change_user_timestamp', 'user_id', 'timestamp'),
        Index('ix_role_change_new_role', 'new_role', 'timestamp'),
        Index('ix_role_change_status', 'status', 'timestamp'),
        Index('ix_role_change_triggered_by', 'triggered_by', 'timestamp'),
    )
    
    def to_dict(self):
        """Convert role change event to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "old_role": self.old_role,
            "new_role": self.new_role,
            "triggered_by": str(self.triggered_by) if self.triggered_by else None,
            "trigger_source": self.trigger_source,
            "approval_required": self.approval_required,
            "approved_by": str(self.approved_by) if self.approved_by else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "reason": self.reason,
            "business_justification": self.business_justification,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "user_agent": self.user_agent,
            "session_id": self.session_id,
            "status": self.status,
            "error_message": self.error_message,
            "rollback_reason": self.rollback_reason,
            "rolled_back_at": self.rolled_back_at.isoformat() if self.rolled_back_at else None,
            "rolled_back_by": str(self.rolled_back_by) if self.rolled_back_by else None,
            "additional_data": self.additional_data,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }