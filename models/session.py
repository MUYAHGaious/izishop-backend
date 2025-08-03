import uuid
import secrets
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Boolean, Text, Integer
from sqlalchemy.orm import relationship
from database.base import Base

class UserSession(Base):
    """
    Secure session model following best practices
    Stores session data server-side with proper entropy
    """
    __tablename__ = "user_sessions"

    # Secure session ID with 64+ bits of entropy
    session_id = Column(String(64), primary_key=True, index=True)
    
    # User reference
    user_id = Column(String, nullable=False, index=True)
    
    # Session metadata
    ip_address = Column(String(45), nullable=True)  # Supports IPv6
    user_agent = Column(Text, nullable=True)
    
    # Session timing (absolute and idle timeouts)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    # Session state
    is_active = Column(Boolean, default=True, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    
    # Session data (encrypted JSON)
    session_data = Column(Text, nullable=True)
    
    # Security tracking
    login_attempts = Column(Integer, default=0)
    last_login_attempt = Column(DateTime, nullable=True)
    
    def __init__(self, user_id: str, ip_address: str = None, user_agent: str = None, 
                 session_lifetime_hours: int = 24):
        """
        Create secure session with proper entropy
        Following OWASP session management guidelines
        """
        # Generate cryptographically secure session ID (64 bits+ entropy)
        self.session_id = self._generate_secure_session_id()
        self.user_id = user_id
        self.ip_address = ip_address
        self.user_agent = user_agent
        
        # Set session timeouts
        now = datetime.utcnow()
        self.created_at = now
        self.last_activity = now
        self.expires_at = now + timedelta(hours=session_lifetime_hours)
        
        self.is_active = True
        self.is_revoked = False
        self.login_attempts = 0
    
    def _generate_secure_session_id(self) -> str:
        """
        Generate cryptographically secure session ID
        - Uses secrets module (CSPRNG)
        - 64+ bits of entropy (32 bytes = 256 bits)
        - URL-safe base64 encoding
        """
        # Generate 32 random bytes (256 bits of entropy)
        random_bytes = secrets.token_bytes(32)
        
        # Convert to URL-safe base64 string (64 characters)
        session_id = secrets.token_urlsafe(32)
        
        return session_id
    
    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
    
    def is_expired(self) -> bool:
        """Check if session has expired (absolute timeout)"""
        return datetime.utcnow() > self.expires_at
    
    def is_idle_expired(self, idle_timeout_minutes: int = 30) -> bool:
        """Check if session has idle timeout"""
        if not self.last_activity:
            return True
        
        idle_threshold = datetime.utcnow() - timedelta(minutes=idle_timeout_minutes)
        return self.last_activity < idle_threshold
    
    def revoke(self):
        """Revoke session immediately"""
        self.is_active = False
        self.is_revoked = True
    
    def extend_session(self, hours: int = 24):
        """Extend session expiry time"""
        self.expires_at = datetime.utcnow() + timedelta(hours=hours)
        self.update_activity()
    
    def is_valid(self, idle_timeout_minutes: int = 30) -> bool:
        """
        Check if session is valid
        - Not expired (absolute timeout)
        - Not idle expired
        - Still active and not revoked
        """
        return (
            self.is_active and 
            not self.is_revoked and 
            not self.is_expired() and 
            not self.is_idle_expired(idle_timeout_minutes)
        )
    
    @classmethod
    def generate_session_name(cls) -> str:
        """
        Generate generic session cookie name to prevent fingerprinting
        As recommended in session handling best practices
        """
        return "sid"  # Generic name instead of framework-specific names