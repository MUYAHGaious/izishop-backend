"""
Enterprise Security Middleware
Implements comprehensive security measures including rate limiting, input validation,
and security headers for production deployment.
"""

import time
import hashlib
import json
import logging
from typing import Dict, List, Optional, Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis
from core.security_config import get_security_settings

logger = logging.getLogger(__name__)

class SecurityMiddleware(BaseHTTPMiddleware):
    """Base security middleware class"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.settings = get_security_settings()

class RateLimitMiddleware(SecurityMiddleware):
    """Rate limiting middleware using Redis"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.redis_client = None
        self._setup_redis()
    
    def _setup_redis(self):
        """Setup Redis connection for rate limiting"""
        try:
            self.redis_client = redis.from_url(
                self.settings.REDIS_URL,
                password=self.settings.REDIS_PASSWORD,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Redis connection established for rate limiting")
        except Exception as e:
            logger.warning(f"Redis connection failed, rate limiting disabled: {e}")
            self.redis_client = None
    
    def _get_client_identifier(self, request: Request) -> str:
        """Get unique identifier for rate limiting"""
        # Use X-Forwarded-For for proxy support
        client_ip = request.headers.get("X-Forwarded-For", request.client.host)
        
        # Add user agent for additional uniqueness
        user_agent = request.headers.get("User-Agent", "")
        
        # Create hash for privacy
        identifier = hashlib.sha256(
            f"{client_ip}:{user_agent}".encode()
        ).hexdigest()
        
        return f"rate_limit:{identifier}"
    
    def _check_rate_limit(self, request: Request) -> bool:
        """Check if request is within rate limits"""
        if not self.redis_client:
            return True  # Allow if Redis is unavailable
        
        try:
            identifier = self._get_client_identifier(request)
            current_time = int(time.time())
            
            # Get current request count
            key = f"{identifier}:{current_time // 60}"  # Per-minute window
            current_count = self.redis_client.get(key)
            
            if current_count is None:
                # First request in this window
                self.redis_client.setex(key, 60, 1)
                return True
            
            current_count = int(current_count)
            
            if current_count >= self.settings.RATE_LIMIT_REQUESTS_PER_MINUTE:
                logger.warning(f"Rate limit exceeded for {identifier}")
                return False
            
            # Increment counter
            self.redis_client.incr(key)
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting error: {e}")
            return True  # Allow on error
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting"""
        if not self._check_rate_limit(request):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests, please try again later",
                    "retry_after": 60
                },
                headers={"Retry-After": "60"}
            )
        
        return await call_next(request)

class SecurityHeadersMiddleware(SecurityMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response"""
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        # Content Security Policy
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp_policy
        
        # HSTS for HTTPS
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response

class InputValidationMiddleware(SecurityMiddleware):
    """Validate and sanitize input data"""
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.suspicious_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"vbscript:",
            r"onload=",
            r"onerror=",
            r"onclick=",
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>",
            r"union\s+select",
            r"drop\s+table",
            r"delete\s+from",
            r"insert\s+into",
            r"update\s+set",
        ]
    
    def _is_suspicious_input(self, value: str) -> bool:
        """Check if input contains suspicious patterns"""
        import re
        
        if not isinstance(value, str):
            return False
        
        value_lower = value.lower()
        
        for pattern in self.suspicious_patterns:
            if re.search(pattern, value_lower, re.IGNORECASE):
                return True
        
        return False
    
    def _sanitize_input(self, data: any) -> any:
        """Recursively sanitize input data"""
        if isinstance(data, dict):
            return {k: self._sanitize_input(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_input(item) for item in data]
        elif isinstance(data, str):
            # Basic HTML escaping
            return (data
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#x27;"))
        else:
            return data
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Validate and sanitize input"""
        try:
            # Check query parameters
            for key, value in request.query_params.items():
                if self._is_suspicious_input(str(value)):
                    logger.warning(f"Suspicious input detected in query param {key}: {value}")
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": "Invalid input detected"}
                    )
            
            # Check headers
            for key, value in request.headers.items():
                if self._is_suspicious_input(str(value)):
                    logger.warning(f"Suspicious input detected in header {key}: {value}")
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"error": "Invalid input detected"}
                    )
            
            # For POST/PUT requests, check body
            # if request.method in ["POST", "PUT", "PATCH"]:
            #     try:
            #         body = await request.body()
            #         if body:
            #             # Try to parse as JSON
            #             try:
            #                 json_data = json.loads(body.decode())
            #                 sanitized_data = self._sanitize_input(json_data)
            #                 # Store sanitized data for later use
            #                 request.state.sanitized_body = sanitized_data
            #             except json.JSONDecodeError:
            #                 # Not JSON, check as string
            #                 body_str = body.decode()
            #                 if self._is_suspicious_input(body_str):
            #                     logger.warning(f"Suspicious input detected in request body")
            #                     return JSONResponse(
            #                         status_code=status.HTTP_400_BAD_REQUEST,
            #                         content={"error": "Invalid input detected"}
            #                     )
            #     except Exception as e:
            #         logger.error(f"Error processing request body: {e}")
            
            return await call_next(request)
            
        except Exception as e:
            logger.error(f"Input validation error: {e}")
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"error": "Internal server error"}
            )

class RequestLoggingMiddleware(SecurityMiddleware):
    """Log all requests for security monitoring"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request details"""
        start_time = time.time()
        
        # Log request
        logger.info(
            f"Request: {request.method} {request.url.path} "
            f"from {request.client.host} "
            f"User-Agent: {request.headers.get('User-Agent', 'Unknown')}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log response
        logger.info(
            f"Response: {request.method} {request.url.path} "
            f"Status: {response.status_code} "
            f"Time: {process_time:.3f}s"
        )
        
        # Add processing time header
        response.headers["X-Process-Time"] = str(process_time)
        
        return response

class CORSMiddleware(SecurityMiddleware):
    """Configure CORS with security best practices"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Handle CORS preflight and add CORS headers"""
        
        # Handle OPTIONS preflight request
        if request.method == "OPTIONS":
            # Get allowed origins
            allowed_origins = self.settings.get_cors_origins()
            
            # Get origin from request
            origin = request.headers.get("Origin")
            
            # Create preflight response
            response = JSONResponse(
                status_code=200,
                content={"message": "CORS preflight successful"}
            )
            
            # Add CORS headers
            if origin and origin in allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = origin
            elif "*" in allowed_origins:
                response.headers["Access-Control-Allow-Origin"] = "*"
            
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Max-Age"] = "86400"
            
            return response
        
        # For non-OPTIONS requests, process normally and add CORS headers
        response = await call_next(request)
        
        # Get allowed origins
        allowed_origins = self.settings.get_cors_origins()
        
        # Get origin from request
        origin = request.headers.get("Origin")
        
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
        elif "*" in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = "*"
        
        # CORS headers
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "86400"
        
        return response

def create_security_middleware_stack(app: ASGIApp) -> ASGIApp:
    """Create and apply security middleware stack"""
    
    # Apply middleware in order (last applied = first executed)
    app = CORSMiddleware(app)
    app = RequestLoggingMiddleware(app)
    app = InputValidationMiddleware(app)
    app = SecurityHeadersMiddleware(app)
    app = RateLimitMiddleware(app)
    
    logger.info("Security middleware stack configured")
    return app 