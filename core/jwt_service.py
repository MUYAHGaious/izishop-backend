"""
Enterprise JWT Token Service
Secure token generation, validation, and management
"""
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from core.security_config import get_security_settings


class JWTService:
    """Enterprise JWT token management service"""
    
    def __init__(self):
        self.settings = get_security_settings()
    
    def create_access_token(
        self,
        user_id: str,
        email: str,
        role: str = "user",
        permissions: List[str] = None,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a secure JWT access token"""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )
        
        payload = {
            "user_id": user_id,
            "email": email,
            "role": role,
            "permissions": permissions or [],
            "is_active": True,
            "token_type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "aud": self.settings.JWT_AUDIENCE,
            "iss": self.settings.JWT_ISSUER,
        }
        
        return jwt.encode(
            payload,
            self.settings.SECRET_KEY,
            algorithm=self.settings.JWT_ALGORITHM
        )
    
    def create_refresh_token(
        self,
        user_id: str,
        email: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a refresh token for token renewal"""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS
            )
        
        payload = {
            "user_id": user_id,
            "email": email,
            "token_type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "aud": self.settings.JWT_AUDIENCE,
            "iss": self.settings.JWT_ISSUER,
        }
        
        return jwt.encode(
            payload,
            self.settings.SECRET_KEY,
            algorithm=self.settings.JWT_ALGORITHM
        )
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.settings.SECRET_KEY,
                algorithms=[self.settings.JWT_ALGORITHM],
                audience=self.settings.JWT_AUDIENCE,
                issuer=self.settings.JWT_ISSUER,
                options={"verify_exp": True}
            )
            
            # Additional payload validation
            required_fields = ["user_id", "email", "exp", "iat"]
            for field in required_fields:
                if field not in payload:
                    return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except Exception:
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Generate new access token from refresh token"""
        payload = self.verify_token(refresh_token)
        
        if not payload or payload.get("token_type") != "refresh":
            return None
        
        # Create new access token with user info from refresh token
        return self.create_access_token(
            user_id=payload["user_id"],
            email=payload["email"],
            role=payload.get("role", "user"),
            permissions=payload.get("permissions", [])
        )
    
    def create_admin_token(
        self,
        user_id: str,
        email: str,
        expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create admin token with elevated permissions"""
        return self.create_access_token(
            user_id=user_id,
            email=email,
            role="admin",
            permissions=["admin", "read", "write", "delete"],
            expires_delta=expires_delta
        )
    
    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get token information without verification (for debugging)"""
        try:
            # Decode without verification for inspection
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False}
            )
            return payload
        except:
            return None


# Global JWT service instance
jwt_service = JWTService()