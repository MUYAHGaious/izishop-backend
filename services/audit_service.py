"""
Audit Service for comprehensive system tracking
Implements enterprise-grade audit logging with security best practices
"""

from typing import Dict, Any, List, Optional, Union
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func, text
from ipaddress import ip_address, IPv4Address, IPv6Address
import logging
import json

from models.audit_log import AuditLog, RoleChangeEvent, AuditAction, ResourceType
from models.user import User
from core.event_system import SystemEvent, EventType, event_handler

logger = logging.getLogger(__name__)

class AuditService:
    """Service for managing audit logs and compliance tracking"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def log_action(
        self,
        action: str,
        resource_type: str,
        user_id: Optional[UUID] = None,
        resource_id: Optional[str] = None,
        resource_name: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        error_code: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None,
        request_method: Optional[str] = None,
        request_path: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        actor_type: str = "user",
        actor_name: Optional[str] = None
    ) -> AuditLog:
        """Log an audit event"""
        
        # Validate and sanitize IP address
        validated_ip = None
        if ip_address:
            try:
                validated_ip = str(ip_address)
            except Exception:
                logger.warning(f"Invalid IP address provided: {ip_address}")
        
        # Generate changes summary
        changes_summary = None
        if old_value and new_value:
            changes_summary = self._generate_changes_summary(old_value, new_value)
        
        # Get actor name if not provided
        if not actor_name and user_id:
            user = self.db.query(User).filter(User.id == str(user_id)).first()
            if user:
                actor_name = f"{user.first_name} {user.last_name}".strip() or user.email
        
        audit_log = AuditLog(
            user_id=user_id,
            actor_type=actor_type,
            actor_name=actor_name,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            old_value=old_value,
            new_value=new_value,
            changes_summary=changes_summary,
            ip_address=validated_ip,
            user_agent=user_agent,
            session_id=session_id,
            request_id=request_id,
            request_method=request_method,
            request_path=request_path,
            success=success,
            error_message=error_message,
            error_code=error_code,
            duration_ms=duration_ms,
            additional_data=metadata or {},
            tags=','.join(tags) if tags else None
        )
        
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)
        
        logger.info(f"Audit log created: {action} on {resource_type} by {actor_name or user_id}")
        return audit_log
    
    async def log_role_change(
        self,
        user_id: UUID,
        old_role: str,
        new_role: str,
        triggered_by: Optional[UUID] = None,
        trigger_source: str = "user_request",
        reason: Optional[str] = None,
        business_justification: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RoleChangeEvent:
        """Log a role change event with detailed tracking"""
        
        role_change = RoleChangeEvent(
            user_id=user_id,
            old_role=old_role,
            new_role=new_role,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            reason=reason,
            business_justification=business_justification,
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            additional_data=metadata or {}
        )
        
        self.db.add(role_change)
        
        # Also create a general audit log
        await self.log_action(
            action=AuditAction.ROLE_UPGRADE.value,
            resource_type=ResourceType.USER.value,
            user_id=triggered_by or user_id,
            resource_id=str(user_id),
            old_value={"role": old_role},
            new_value={"role": new_role},
            ip_address=ip_address,
            user_agent=user_agent,
            session_id=session_id,
            additional_data={
                "trigger_source": trigger_source,
                "reason": reason,
                **(metadata or {})
            },
            tags=["role_change", "security", new_role.lower()]
        )
        
        self.db.commit()
        self.db.refresh(role_change)
        
        logger.info(f"Role change logged: {user_id} from {old_role} to {new_role}")
        return role_change
    
    async def log_permission_check(
        self,
        user_id: UUID,
        permission: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        granted: bool = False,
        context: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        session_id: Optional[str] = None
    ):
        """Log permission checks for security auditing"""
        
        action = AuditAction.PERMISSION_GRANTED.value if granted else AuditAction.ACCESS_DENIED.value
        
        await self.log_action(
            action=action,
            resource_type=resource_type,
            user_id=user_id,
            resource_id=resource_id,
            success=granted,
            error_message=f"Access denied for permission: {permission}" if not granted else None,
            ip_address=ip_address,
            session_id=session_id,
            additional_data={
                "permission": permission,
                "context": context or {}
            },
            tags=["permission_check", "security", "access_control"]
        )
    
    async def log_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log security-related events"""
        
        await self.log_action(
            action=event_type,
            resource_type=ResourceType.SYSTEM.value,
            user_id=user_id,
            success=False,
            error_message=description,
            ip_address=ip_address,
            user_agent=user_agent,
            additional_data={
                "severity": severity,
                "event_type": event_type,
                **(metadata or {})
            },
            tags=["security", "alert", severity.lower()]
        )
    
    async def get_user_audit_trail(
        self,
        user_id: UUID,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        success_only: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get audit trail for a specific user"""
        
        query = self.db.query(AuditLog).filter(AuditLog.user_id == user_id)
        
        # Apply filters
        if date_from:
            query = query.filter(AuditLog.timestamp >= date_from)
        if date_to:
            query = query.filter(AuditLog.timestamp <= date_to)
        if action:
            query = query.filter(AuditLog.action == action)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if success_only is not None:
            query = query.filter(AuditLog.success == success_only)
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination and ordering
        logs = query.order_by(desc(AuditLog.timestamp))\
                  .offset(offset)\
                  .limit(limit)\
                  .all()
        
        return {
            "audit_logs": [log.to_dict() for log in logs],
            "total_count": total_count,
            "has_more": (offset + limit) < total_count
        }
    
    async def get_role_change_history(
        self,
        user_id: Optional[UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        role: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get role change history"""
        
        query = self.db.query(RoleChangeEvent)
        
        if user_id:
            query = query.filter(RoleChangeEvent.user_id == user_id)
        if date_from:
            query = query.filter(RoleChangeEvent.timestamp >= date_from)
        if date_to:
            query = query.filter(RoleChangeEvent.timestamp <= date_to)
        if role:
            query = query.filter(
                or_(
                    RoleChangeEvent.old_role == role,
                    RoleChangeEvent.new_role == role
                )
            )
        
        total_count = query.count()
        
        events = query.order_by(desc(RoleChangeEvent.timestamp))\
                     .offset(offset)\
                     .limit(limit)\
                     .all()
        
        return {
            "role_changes": [event.to_dict() for event in events],
            "total_count": total_count,
            "has_more": (offset + limit) < total_count
        }
    
    async def get_system_audit_logs(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        user_id: Optional[UUID] = None,
        ip_address: Optional[str] = None,
        success_only: Optional[bool] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get system-wide audit logs (admin only)"""
        
        query = self.db.query(AuditLog)
        
        # Apply filters
        if date_from:
            query = query.filter(AuditLog.timestamp >= date_from)
        if date_to:
            query = query.filter(AuditLog.timestamp <= date_to)
        if action:
            query = query.filter(AuditLog.action == action)
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if ip_address:
            query = query.filter(AuditLog.ip_address == ip_address)
        if success_only is not None:
            query = query.filter(AuditLog.success == success_only)
        if tags:
            for tag in tags:
                query = query.filter(AuditLog.tags.contains(tag))
        
        total_count = query.count()
        
        logs = query.order_by(desc(AuditLog.timestamp))\
                  .offset(offset)\
                  .limit(limit)\
                  .all()
        
        return {
            "audit_logs": [log.to_dict() for log in logs],
            "total_count": total_count,
            "has_more": (offset + limit) < total_count
        }
    
    async def get_security_alerts(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Get security alerts from audit logs"""
        
        query = self.db.query(AuditLog).filter(
            AuditLog.tags.contains("security")
        )
        
        if date_from:
            query = query.filter(AuditLog.timestamp >= date_from)
        if date_to:
            query = query.filter(AuditLog.timestamp <= date_to)
        if severity:
            query = query.filter(AuditLog.tags.contains(severity.lower()))
        
        total_count = query.count()
        
        alerts = query.order_by(desc(AuditLog.timestamp))\
                     .offset(offset)\
                     .limit(limit)\
                     .all()
        
        return {
            "security_alerts": [alert.to_dict() for alert in alerts],
            "total_count": total_count,
            "has_more": (offset + limit) < total_count
        }
    
    async def cleanup_old_logs(self, retention_days: int = 365) -> int:
        """Clean up old audit logs based on retention policy"""
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        
        # Keep security logs longer
        security_cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days * 2)
        
        # Delete non-security logs older than retention period
        count = self.db.query(AuditLog).filter(
            and_(
                AuditLog.timestamp < cutoff_date,
                ~AuditLog.tags.contains("security")
            )
        ).delete(synchronize_session=False)
        
        # Delete old security logs (but keep them longer)
        security_count = self.db.query(AuditLog).filter(
            and_(
                AuditLog.timestamp < security_cutoff,
                AuditLog.tags.contains("security")
            )
        ).delete(synchronize_session=False)
        
        self.db.commit()
        total_deleted = count + security_count
        
        logger.info(f"Deleted {total_deleted} old audit logs (retention: {retention_days} days)")
        return total_deleted
    
    def _generate_changes_summary(self, old_value: Dict[str, Any], new_value: Dict[str, Any]) -> str:
        """Generate a human-readable summary of changes"""
        
        changes = []
        all_keys = set(old_value.keys()) | set(new_value.keys())
        
        for key in all_keys:
            old_val = old_value.get(key)
            new_val = new_value.get(key)
            
            if old_val != new_val:
                if old_val is None:
                    changes.append(f"Added {key}: {new_val}")
                elif new_val is None:
                    changes.append(f"Removed {key}: {old_val}")
                else:
                    changes.append(f"Changed {key}: {old_val} → {new_val}")
        
        return "; ".join(changes) if changes else "No changes detected"

# Event handlers for automatic audit logging
@event_handler(EventType.ROLE_UPGRADED)
async def handle_role_upgrade_audit(event: SystemEvent):
    """Handle role upgrade events by creating audit logs"""
    from database import get_db
    
    db = next(get_db())
    audit_service = AuditService(db)
    
    try:
        user_id = UUID(event.data["user_id"])
        old_role = event.data["old_role"]
        new_role = event.data["new_role"]
        trigger_source = event.data["trigger_source"]
        triggered_by = UUID(event.data["triggered_by"]) if event.data.get("triggered_by") else None
        
        await audit_service.log_role_change(
            user_id=user_id,
            old_role=old_role,
            new_role=new_role,
            triggered_by=triggered_by,
            trigger_source=trigger_source,
            ip_address=event.metadata.ip_address,
            user_agent=event.metadata.user_agent,
            session_id=event.metadata.session_id,
            additional_data=event.metadata.additional_data
        )
        
        logger.info(f"Created audit log for role upgrade: {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to create role upgrade audit log: {e}")
    finally:
        db.close()