"""
Enterprise CORS Configuration
Secure Cross-Origin Resource Sharing settings
"""
from typing import List, Union
from fastapi.middleware.cors import CORSMiddleware
from core.security_config import get_security_settings


def get_cors_settings() -> dict:
    """Get secure CORS configuration based on environment"""
    settings = get_security_settings()
    
    if settings.is_production():
        # Production CORS settings - restrictive
        return {
            "allow_origins": settings.get_cors_origins(),
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH"],
            "allow_headers": [
                "Authorization",
                "Content-Type",
                "Accept",
                "X-Requested-With",
                "X-Request-ID",
                "Cache-Control"
            ],
            "expose_headers": [
                "X-Request-ID",
                "X-Process-Time",
                "X-Rate-Limit-Remaining",
                "X-Rate-Limit-Reset"
            ],
            "max_age": 86400,  # 24 hours
        }
    else:
        # Development CORS settings - more permissive but still secure
        return {
            "allow_origins": [
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:4028",
                "http://127.0.0.1:4028",
                "http://localhost:5173",  # Vite dev server
                "http://127.0.0.1:5173",
                "https://izishop-frontend.onrender.com",  # Production frontend
                "https://izishop-backend.onrender.com"    # Production backend
            ],
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": [
                "Authorization",
                "Content-Type",
                "Accept",
                "X-Requested-With",
                "X-Request-ID",
                "Cache-Control",
                "Origin",
                "X-CSRF-Token"
            ],
            "expose_headers": [
                "X-Request-ID",
                "X-Process-Time",
                "X-Rate-Limit-Remaining",
                "X-Rate-Limit-Reset"
            ],
            "max_age": 3600,  # 1 hour for development
        }


def configure_cors(app) -> None:
    """Configure CORS middleware with secure settings"""
    cors_settings = get_cors_settings()
    
    app.add_middleware(
        CORSMiddleware,
        **cors_settings
    )


def validate_origin(origin: str) -> bool:
    """Validate if origin is allowed"""
    settings = get_security_settings()
    allowed_origins = settings.get_cors_origins()
    
    if not origin:
        return False
    
    # Check exact match
    if origin in allowed_origins:
        return True
    
    # In development, allow localhost variants
    if not settings.is_production():
        if origin.startswith(("http://localhost:", "http://127.0.0.1:")):
            return True
    
    return False


class SecureCORSMiddleware(CORSMiddleware):
    """Enhanced CORS middleware with additional security checks"""
    
    def __init__(self, app, **kwargs):
        super().__init__(app, **kwargs)
        self.settings = get_security_settings()
    
    def is_allowed_origin(self, origin: str) -> bool:
        """Enhanced origin validation with security checks"""
        if not origin:
            return False
        
        # Security check: prevent dangerous origins
        dangerous_patterns = [
            "javascript:",
            "data:",
            "vbscript:",
            "file:",
            "ftp:"
        ]
        
        if any(origin.lower().startswith(pattern) for pattern in dangerous_patterns):
            return False
        
        # Check against allowed origins
        return super().is_allowed_origin(origin)
    
    async def dispatch(self, request, call_next):
        """Enhanced CORS handling with security logging"""
        origin = request.headers.get("Origin")
        
        if origin and not self.is_allowed_origin(origin):
            # Log potential CORS violation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"CORS violation attempted from origin: {origin}")
        
        return await super().dispatch(request, call_next)