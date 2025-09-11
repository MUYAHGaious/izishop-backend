"""
Enhanced Role Management Service for IziShop
Implements enterprise-grade role management with immutable upgrades
"""

from typing import Dict, Any, List, Optional, Set
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
import logging

from models.user import User
from models.shop import Shop
from models.audit_log import AuditAction, ResourceType
from services.audit_service import AuditService
from services.notification_service import NotificationService
from core.event_system import (
    event_bus, 
    RoleUpgradeEvent, 
    SystemEvent, 
    EventType, 
    EventMetadata
)

logger = logging.getLogger(__name__)

class RoleUpgradeError(Exception):
    """Exception raised when role upgrade fails"""
    pass

class RoleManager:
    """Enhanced role management with security and compliance"""
    
    # Role hierarchy (higher number = more privileges)
    ROLE_HIERARCHY = {
        "CUSTOMER": 0,
        "CASUAL_SELLER": 1,
        "DELIVERY_AGENT": 1,
        "SHOP_OWNER": 2,
        "ADMIN": 3
    }
    
    # Upgrade rules - defines allowed upgrade paths
    UPGRADE_RULES = {
        "CUSTOMER": ["CASUAL_SELLER", "DELIVERY_AGENT", "SHOP_OWNER"],
        "CASUAL_SELLER": ["SHOP_OWNER"],  # Can upgrade to full shop owner
        "DELIVERY_AGENT": [],  # Terminal role for delivery agents
        "SHOP_OWNER": [],      # Terminal role for shop owners
        "ADMIN": []            # Terminal role for admins
    }
    
    # Role requirements - conditions that must be met for upgrade
    ROLE_REQUIREMENTS = {
        "SHOP_OWNER": {
            "min_account_age_days": 0,  # Immediate upgrade allowed for development
            "email_verified": True,
            "phone_verified": False,  # Not required for development
            "profile_complete": 70,   # 70% profile completion
            "terms_accepted": True
        },
        "DELIVERY_AGENT": {
            "min_account_age_days": 7,
            "email_verified": True,
            "phone_verified": True,
            "profile_complete": 90,
            "terms_accepted": True,
            "background_check": False  # Disabled for development
        },
        "ADMIN": {
            "min_account_age_days": 30,
            "email_verified": True,
            "phone_verified": True,
            "profile_complete": 100,
            "terms_accepted": True,
            "admin_approval": True
        }
    }
    
    # Role permissions mapping
    ROLE_PERMISSIONS = {
        "CUSTOMER": {
            "orders": ["create", "view_own", "cancel_own"],
            "profile": ["view_own", "edit_own"],
            "products": ["view", "search"],
            "cart": ["manage_own"],
            "wishlist": ["manage_own"],
            "reviews": ["create", "view", "edit_own"]
        },
        "CASUAL_SELLER": {
            "orders": ["create", "view_own", "cancel_own"],
            "profile": ["view_own", "edit_own"],
            "products": ["view", "search", "list_limited"],
            "cart": ["manage_own"],
            "wishlist": ["manage_own"],
            "reviews": ["create", "view", "edit_own"],
            "casual_listings": ["create", "manage_own"]
        },
        "DELIVERY_AGENT": {
            "orders": ["view_assigned", "update_assigned"],
            "profile": ["view_own", "edit_own"],
            "products": ["view", "search"],
            "delivery": ["accept", "manage_assigned", "track"],
            "earnings": ["view_own"]
        },
        "SHOP_OWNER": {
            "orders": ["view_shop", "manage_shop", "fulfill"],
            "profile": ["view_own", "edit_own"],
            "products": ["create", "manage_own", "view", "search"],
            "shop": ["create", "manage_own", "analytics"],
            "inventory": ["manage_own"],
            "customers": ["view_shop_customers", "communicate"],
            "analytics": ["view_shop"],
            "marketing": ["manage_shop_campaigns"]
        },
        "ADMIN": {
            "users": ["view_all", "manage_all", "suspend", "activate"],
            "shops": ["view_all", "approve", "reject", "suspend"],
            "products": ["view_all", "moderate", "remove"],
            "orders": ["view_all", "manage_all"],
            "analytics": ["view_all", "export"],
            "system": ["configure", "maintain"],
            "content": ["moderate", "remove"],
            "reports": ["generate", "export"]
        }
    }
    
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)
    
    async def upgrade_user_role(
        self,
        user_id: UUID,
        new_role: str,
        triggered_by: Optional[UUID] = None,
        trigger_source: str = "user_request",
        reason: Optional[str] = None,
        bypass_requirements: bool = False,
        metadata: Optional[EventMetadata] = None
    ) -> Dict[str, Any]:
        """Upgrade a user's role with comprehensive validation and tracking"""
        
        # Get the user
        user = self.db.query(User).filter(User.id == str(user_id)).first()
        if not user:
            raise RoleUpgradeError("User not found")
        
        old_role = user.role
        
        # Validate upgrade path
        if not self.can_upgrade_to(old_role, new_role):
            raise RoleUpgradeError(
                f"Cannot upgrade from {old_role} to {new_role}. "
                f"Allowed upgrades: {self.get_available_upgrades(old_role)}"
            )
        
        # Check if already has the role
        if old_role == new_role:
            raise RoleUpgradeError(f"User already has role {new_role}")
        
        # Validate requirements (unless bypassed for development)
        if not bypass_requirements:
            validation_result = await self.validate_role_requirements(user, new_role)
            if not validation_result["valid"]:
                raise RoleUpgradeError(
                    f"Requirements not met: {', '.join(validation_result['missing_requirements'])}"
                )
        
        # Begin transaction
        try:
            # Update user role
            user.role = new_role
            user.role_changed_at = datetime.now(timezone.utc)
            user.role_changed_by = str(triggered_by) if triggered_by else str(user_id)
            
            # Create role change event for detailed tracking
            role_change = await self.audit_service.log_role_change(
                user_id=user_id,
                old_role=old_role,
                new_role=new_role,
                triggered_by=triggered_by,
                trigger_source=trigger_source,
                reason=reason,
                ip_address=metadata.ip_address if metadata else None,
                user_agent=metadata.user_agent if metadata else None,
                session_id=metadata.session_id if metadata else None,
                metadata=metadata.additional_data if metadata else None
            )
            
            # Handle role-specific setup
            role_specific_result = await self._handle_role_specific_setup(user, new_role)
            
            # Commit all changes
            self.db.commit()
            
            # Emit role upgrade event
            upgrade_event = RoleUpgradeEvent(
                user_id=user_id,
                old_role=old_role,
                new_role=new_role,
                trigger_source=trigger_source,
                triggered_by=triggered_by,
                metadata=metadata or EventMetadata()
            )
            
            await event_bus.emit_event(upgrade_event)
            
            logger.info(f"Role upgrade successful: {user_id} from {old_role} to {new_role}")
            
            return {
                "success": True,
                "message": f"Role upgraded to {new_role} successfully",
                "old_role": old_role,
                "new_role": new_role,
                "user_id": str(user_id),
                "role_change_id": str(role_change.id),
                "requires_refresh": True,
                "additional_setup": role_specific_result
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Role upgrade failed: {e}")
            
            # Emit failure event
            failure_event = SystemEvent(
                event_type=EventType.ROLE_UPGRADE_FAILED,
                data={
                    "user_id": str(user_id),
                    "target_role": new_role,
                    "current_role": old_role,
                    "reason": str(e),
                    "trigger_source": trigger_source,
                    "triggered_by": str(triggered_by) if triggered_by else None
                },
                metadata=metadata or EventMetadata()
            )
            
            await event_bus.emit_event(failure_event)
            raise
    
    def can_upgrade_to(self, current_role: str, target_role: str) -> bool:
        """Check if a role can be upgraded to another role"""
        if current_role not in self.UPGRADE_RULES:
            return False
        
        return target_role in self.UPGRADE_RULES[current_role]
    
    def get_available_upgrades(self, current_role: str) -> List[str]:
        """Get list of available role upgrades for current role"""
        return self.UPGRADE_RULES.get(current_role, [])
    
    def get_role_level(self, role: str) -> int:
        """Get the hierarchy level of a role"""
        return self.ROLE_HIERARCHY.get(role, -1)
    
    def is_higher_role(self, role1: str, role2: str) -> bool:
        """Check if role1 has higher privileges than role2"""
        return self.get_role_level(role1) > self.get_role_level(role2)
    
    def has_permission(self, role: str, resource: str, action: str) -> bool:
        """Check if a role has a specific permission"""
        permissions = self.ROLE_PERMISSIONS.get(role, {})
        resource_permissions = permissions.get(resource, [])
        return action in resource_permissions
    
    def get_role_permissions(self, role: str) -> Dict[str, List[str]]:
        """Get all permissions for a role"""
        return self.ROLE_PERMISSIONS.get(role, {})
    
    async def validate_role_requirements(
        self, 
        user: User, 
        target_role: str
    ) -> Dict[str, Any]:
        """Validate if user meets requirements for target role"""
        
        requirements = self.ROLE_REQUIREMENTS.get(target_role, {})
        missing_requirements = []
        
        # Check minimum account age
        if requirements.get("min_account_age_days", 0) > 0:
            account_age = (datetime.now(timezone.utc) - user.created_at).days
            if account_age < requirements["min_account_age_days"]:
                missing_requirements.append(
                    f"Account must be at least {requirements['min_account_age_days']} days old"
                )
        
        # Check email verification
        if requirements.get("email_verified", False) and not user.is_email_verified:
            missing_requirements.append("Email must be verified")
        
        # Check phone verification
        if requirements.get("phone_verified", False) and not user.is_phone_verified:
            missing_requirements.append("Phone number must be verified")
        
        # Check profile completion
        if requirements.get("profile_complete", 0) > 0:
            completion_score = self._calculate_profile_completion(user)
            if completion_score < requirements["profile_complete"]:
                missing_requirements.append(
                    f"Profile must be at least {requirements['profile_complete']}% complete "
                    f"(currently {completion_score}%)"
                )
        
        return {
            "valid": len(missing_requirements) == 0,
            "missing_requirements": missing_requirements,
            "requirements_met": len(requirements) - len(missing_requirements),
            "total_requirements": len(requirements)
        }
    
    async def _handle_role_specific_setup(
        self, 
        user: User, 
        new_role: str
    ) -> Dict[str, Any]:
        """Handle role-specific setup after upgrade"""
        
        setup_results = {}
        
        if new_role == "SHOP_OWNER":
            # Check if shop already exists
            existing_shop = self.db.query(Shop).filter(
                Shop.owner_id == user.id
            ).first()
            
            if not existing_shop:
                # Create default shop
                shop_name = f"{user.first_name} {user.last_name}'s Shop".strip()
                if not shop_name or shop_name == "'s Shop":
                    shop_name = f"Shop by {user.email.split('@')[0]}"
                
                new_shop = Shop(
                    owner_id=user.id,
                    name=shop_name,
                    description=f"Welcome to {shop_name}! We're excited to serve you.",
                    address="",
                    phone=user.phone or "",
                    email=user.email,
                    is_active=True,
                    is_verified=False
                )
                
                self.db.add(new_shop)
                self.db.flush()  # Get shop ID
                
                setup_results["shop_created"] = {
                    "shop_id": str(new_shop.id),
                    "shop_name": shop_name
                }
                
                # Emit shop creation event
                shop_event = SystemEvent(
                    event_type=EventType.SHOP_CREATED,
                    data={
                        "shop_id": str(new_shop.id),
                        "owner_id": str(user.id),
                        "shop_name": shop_name
                    }
                )
                
                await event_bus.emit_event(shop_event)
                
                logger.info(f"Created shop {shop_name} for new shop owner {user.id}")
            else:
                setup_results["existing_shop"] = {
                    "shop_id": str(existing_shop.id),
                    "shop_name": existing_shop.name
                }
        
        return setup_results
    
    def _calculate_profile_completion(self, user: User) -> int:
        """Calculate user profile completion percentage"""
        
        fields_to_check = [
            user.first_name,
            user.last_name,
            user.email,
            user.phone,
            # Add more fields as needed
        ]
        
        completed_fields = sum(1 for field in fields_to_check if field)
        completion_percentage = int((completed_fields / len(fields_to_check)) * 100)
        
        # Add bonus for verified email/phone
        if user.is_email_verified:
            completion_percentage += 10
        if user.is_phone_verified:
            completion_percentage += 10
        
        return min(completion_percentage, 100)
    
    async def get_role_statistics(self) -> Dict[str, Any]:
        """Get statistics about role distribution"""
        
        role_counts = {}
        for role in self.ROLE_HIERARCHY.keys():
            count = self.db.query(User).filter(User.role == role).count()
            role_counts[role] = count
        
        total_users = sum(role_counts.values())
        
        return {
            "total_users": total_users,
            "role_counts": role_counts,
            "role_percentages": {
                role: round((count / total_users * 100), 2) if total_users > 0 else 0
                for role, count in role_counts.items()
            }
        }
    
    async def get_recent_role_changes(
        self, 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent role changes for monitoring"""
        
        recent_changes = await self.audit_service.get_role_change_history(
            limit=limit,
            offset=0
        )
        
        return recent_changes["role_changes"]