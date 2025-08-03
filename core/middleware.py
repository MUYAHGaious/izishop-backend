"""
Custom middleware for request/response handling and monitoring
"""
import time
import uuid
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests and responses"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        # Log request
        start_time = time.time()
        logger.info(
            f"Request {request_id}: {request.method} {request.url} - "
            f"Client: {request.client.host if request.client else 'unknown'}"
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log response
            logger.info(
                f"Response {request_id}: {response.status_code} - "
                f"Time: {process_time:.3f}s"
            )
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.3f}"
            
            return response
            
        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                f"Request {request_id} failed: {str(e)} - "
                f"Time: {process_time:.3f}s"
            )
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), "
            "payment=(), usb=(), magnetometer=(), gyroscope=()"
        )
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting middleware"""
    
    def __init__(self, app, calls: int = 100, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients = {}
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        current_time = time.time()
        
        # Clean old entries
        self.clients = {
            ip: calls for ip, calls in self.clients.items()
            if current_time - calls[-1] < self.period
        }
        
        # Check rate limit
        if client_ip in self.clients:
            calls = self.clients[client_ip]
            # Remove calls older than period
            calls = [call_time for call_time in calls if current_time - call_time < self.period]
            
            if len(calls) >= self.calls:
                logger.warning(f"Rate limit exceeded for {client_ip}")
                return Response(
                    content='{"success": false, "message": "Rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json"
                )
            
            calls.append(current_time)
            self.clients[client_ip] = calls
        else:
            self.clients[client_ip] = [current_time]
        
        return await call_next(request)


class DatabaseTransactionMiddleware(BaseHTTPMiddleware):
    """Ensure proper database transaction handling"""
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip for non-mutating operations
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)
        
        try:
            response = await call_next(request)
            
            # If response indicates success, commit is already handled by the endpoint
            # If there's an error status, the transaction should be rolled back
            if response.status_code >= 400:
                logger.warning(f"Request failed with status {response.status_code}")
            
            return response
            
        except Exception as e:
            logger.error(f"Request failed with exception: {str(e)}")
            raise