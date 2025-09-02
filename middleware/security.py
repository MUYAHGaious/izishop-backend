"""
Security middleware for production deployment
"""
from fastapi import Request, Response
from fastapi.responses import JSONResponse
import time
from typing import Callable


class SecurityHeadersMiddleware:
    """Add security headers to all responses"""
    
    def __init__(self, app, enable_hsts: bool = True):
        self.app = app
        self.enable_hsts = enable_hsts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                
                # Security headers
                security_headers = {
                    b"x-frame-options": b"SAMEORIGIN",
                    b"x-content-type-options": b"nosniff",
                    b"x-xss-protection": b"1; mode=block",
                    b"referrer-policy": b"strict-origin-when-cross-origin",
                    b"permissions-policy": b"geolocation=(), microphone=(), camera=()",
                }
                
                # HSTS header for HTTPS
                if self.enable_hsts:
                    security_headers[b"strict-transport-security"] = b"max-age=31536000; includeSubDomains; preload"
                
                # Content Security Policy
                csp = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com; "
                    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                    "font-src 'self' https://fonts.gstatic.com; "
                    "img-src 'self' data: https:; "
                    "connect-src 'self' https://dsapi.tranzak.me https://www.google-analytics.com; "
                    "frame-src https://dsapi.tranzak.me; "
                    "object-src 'none';"
                )
                security_headers[b"content-security-policy"] = csp.encode()
                
                # Add security headers
                for name, value in security_headers.items():
                    headers[name] = value
                
                message["headers"] = list(headers.items())
            
            await send(message)

        await self.app(scope, receive, send_with_security_headers)


class RequestSizeMiddleware:
    """Limit request size for security"""
    
    def __init__(self, app, max_size: int = 50 * 1024 * 1024):  # 50MB default
        self.app = app
        self.max_size = max_size

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check content-length header
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        
        if content_length:
            try:
                size = int(content_length.decode())
                if size > self.max_size:
                    response = JSONResponse(
                        status_code=413,
                        content={"detail": "Request too large"}
                    )
                    await response(scope, receive, send)
                    return
            except (ValueError, UnicodeDecodeError):
                pass

        await self.app(scope, receive, send)


class RequestTimeoutMiddleware:
    """Add request timeout for security"""
    
    def __init__(self, app, timeout: int = 30):
        self.app = app
        self.timeout = timeout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import asyncio
        
        try:
            await asyncio.wait_for(
                self.app(scope, receive, send),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            response = JSONResponse(
                status_code=408,
                content={"detail": "Request timeout"}
            )
            await response(scope, receive, send)