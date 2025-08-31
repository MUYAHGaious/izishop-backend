"""
Enterprise Authentication Middleware
Secure JWT token validation and user authentication
"""
import jwt
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from core.security_config import get_security_settings
from core.validation import SecurityValidator

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Enhanced JWT authentication middleware with security features"""
    
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_security_settings()
        self.public_paths = {
            "/docs", "/redoc", "/openapi.json", "/health", "/metrics",
            "/auth/login", "/auth/register", "/auth/refresh",
            "/products/search", "/categories", "/shops/public"
        }
        self.admin_paths = {
            "/admin", "/users/all", "/shops/admin", "/analytics"
        }
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        """Process authentication for each request"""
        
        # Skip authentication for public paths
        if self._is_public_path(request.url.path):
            return await call_next(request)
        
        try:
            # Extract and validate token
            token = await self._extract_token(request)
            if not token:
                return self._unauthorized_response("Missing authentication token")
            
            # Validate token format and security
            if not self._is_secure_token(token):
                return self._unauthorized_response("Invalid token format")
            
            # Decode and validate JWT
            payload = await self._decode_token(token)
            if not payload:
                return self._unauthorized_response("Invalid or expired token")
            
            # Validate user and permissions
            user_data = await self._validate_user(payload)
            if not user_data:
                return self._unauthorized_response("User not found or inactive")
            
            # Check admin permissions for admin paths
            if self._is_admin_path(request.url.path):
                if not self._is_admin_user(user_data):
                    return self._forbidden_response("Admin access required")
            
            # Inject user data into request state
            request.state.user = user_data
            request.state.user_id = user_data.get("user_id")
            request.state.user_role = user_data.get("role", "user")
            
            # Log authentication success
            logger.info(f"Authenticated user {user_data.get('user_id')} for {request.url.path}")
            
            return await call_next(request)
            
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return self._unauthorized_response("Authentication failed")
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public and doesn't require authentication"""
        return any(path.startswith(public_path) for public_path in self.public_paths)
    
    def _is_admin_path(self, path: str) -> bool:
        """Check if path requires admin permissions"""
        return any(path.startswith(admin_path) for admin_path in self.admin_paths)
    
    async def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from request headers"""
        # Check Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        
        # Check cookie fallback
        token_cookie = request.cookies.get("access_token")
        if token_cookie:
            return token_cookie
        
        return None
    
    def _is_secure_token(self, token: str) -> bool:
        """Validate token format and detect potential security issues"""
        if not token or len(token) < 20:
            return False
        
        # Check for suspicious patterns
        if SecurityValidator.detect_xss(token) or SecurityValidator.detect_sql_injection(token):
            logger.warning(f"Suspicious token detected: potential security attack")
            return False
        
        # Basic JWT structure check (should have 3 parts separated by dots)
        parts = token.split('.')
        if len(parts) != 3:
            return False
        
        return True
    
    async def _decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate JWT token"""
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
                    logger.warning(f"Token missing required field: {field}")
                    return None
            
            # Check token age (prevent replay attacks with old tokens)
            issued_at = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)
            now = datetime.now(timezone.utc)
            token_age_hours = (now - issued_at).total_seconds() / 3600
            
            if token_age_hours > 24:  # Token older than 24 hours
                logger.warning(f"Token too old: {token_age_hours} hours")
                return None
            
            return payload
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Token decode error: {str(e)}")
            return None
    
    async def _validate_user(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate user exists and is active"""
        try:
            # In a real implementation, this would query the database
            # For now, we'll extract user data from the token payload
            user_data = {
                "user_id": payload.get("user_id"),
                "email": payload.get("email"),
                "role": payload.get("role", "user"),
                "is_active": payload.get("is_active", True),
                "permissions": payload.get("permissions", [])
            }
            
            # Validate user is active
            if not user_data.get("is_active"):
                logger.warning(f"Inactive user attempted access: {user_data.get('email')}")
                return None
            
            return user_data
            
        except Exception as e:
            logger.error(f"User validation error: {str(e)}")
            return None
    
    def _is_admin_user(self, user_data: Dict[str, Any]) -> bool:
        """Check if user has admin privileges"""
        role = user_data.get("role", "").lower()
        permissions = user_data.get("permissions", [])
        
        return role in ["admin", "superuser"] or "admin" in permissions
    
    def _unauthorized_response(self, message: str) -> JSONResponse:
        """Return unauthorized response"""
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "success": False,
                "message": message,
                "error_code": "UNAUTHORIZED"
            },
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    def _forbidden_response(self, message: str) -> JSONResponse:
        """Return forbidden response"""
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "message": message,
                "error_code": "FORBIDDEN"
            }
        )


class TokenBlacklistMiddleware(BaseHTTPMiddleware):
    """Middleware to check for blacklisted tokens (logout, compromised tokens)"""
    
    def __init__(self, app):
        super().__init__(app)
        self.blacklisted_tokens = set()  # In production, use Redis or database
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        """Check if token is blacklisted"""
        
        # Only check authenticated requests
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            
            if token in self.blacklisted_tokens:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        "success": False,
                        "message": "Token has been revoked",
                        "error_code": "TOKEN_REVOKED"
                    }
                )
        
        return await call_next(request)
    
    def blacklist_token(self, token: str):
        """Add token to blacklist"""
        self.blacklisted_tokens.add(token)
        logger.info("Token blacklisted")
    
    def clear_expired_tokens(self):
        """Periodic cleanup of expired tokens from blacklist"""
        # In production, implement with Redis TTL or database cleanup job
        pass


class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """Enhanced session security with anomaly detection"""
    
    def __init__(self, app):
        super().__init__(app)
        self.user_sessions = {}  # In production, use Redis
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        """Monitor session security and detect anomalies"""
        
        # Get user ID from request state (set by AuthenticationMiddleware)
        response = await call_next(request)
        
        if hasattr(request.state, 'user_id') and request.state.user_id:
            await self._update_session_info(request)
        
        return response
    
    async def _update_session_info(self, request: Request):
        """Update and validate session information"""
        user_id = request.state.user_id
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "")
        
        # Initialize session tracking
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                "ips": set(),
                "user_agents": set(),
                "first_seen": datetime.now(timezone.utc),
                "last_seen": datetime.now(timezone.utc),
                "request_count": 0
            }
        
        session = self.user_sessions[user_id]
        session["last_seen"] = datetime.now(timezone.utc)
        session["request_count"] += 1
        
        # Detect IP anomalies
        if client_ip not in session["ips"]:
            if len(session["ips"]) > 0:  # Not first login
                logger.warning(f"New IP detected for user {user_id}: {client_ip}")
            session["ips"].add(client_ip)
        
        # Detect User-Agent anomalies
        if user_agent not in session["user_agents"]:
            if len(session["user_agents"]) > 0:  # Not first login
                logger.warning(f"New User-Agent detected for user {user_id}")
            session["user_agents"].add(user_agent)
        
        # Check for suspicious activity patterns
        if session["request_count"] > 1000:  # High request volume
            logger.warning(f"High request volume for user {user_id}: {session['request_count']}")


# Helper function to get current user from request
def get_current_user(request: Request) -> Optional[Dict[str, Any]]:
    """Get current authenticated user from request state"""
    return getattr(request.state, 'user', None)


# Helper function to require admin access
def require_admin(request: Request) -> bool:
    """Check if current user has admin access"""
    user = get_current_user(request)
    if not user:
        return False
    
    role = user.get("role", "").lower()
    permissions = user.get("permissions", [])
    
    return role in ["admin", "superuser"] or "admin" in permissions