"""
Logging Middleware - Automatically captures all FastAPI requests/responses
"""
import time
import json
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from core.file_logger import file_logger
from typing import Callable

class LoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timing
        start_time = time.time()
        
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # Get request body if it exists
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body = body_bytes.decode('utf-8')
            except Exception:
                body = "[Could not read body]"
        
        # Process the request
        try:
            response = await call_next(request)
            response_time = time.time() - start_time
            
            # Log successful request
            file_logger.log_api_request(
                method=request.method,
                url=str(request.url),
                headers=dict(request.headers),
                body=body,
                status_code=response.status_code,
                response_time=response_time,
                client_ip=client_ip
            )
            
            return response
            
        except Exception as e:
            response_time = time.time() - start_time
            
            # Log failed request
            file_logger.log_api_request(
                method=request.method,
                url=str(request.url),
                headers=dict(request.headers),
                body=body,
                status_code=500,
                response_time=response_time,
                client_ip=client_ip
            )
            
            # Log the error
            file_logger.log_error(
                error=e,
                context=f"{request.method} {request.url}",
                extra_data={
                    "client_ip": client_ip,
                    "request_body": body,
                    "headers": dict(request.headers)
                }
            )
            
            # Return error response
            return JSONResponse(
                status_code=500,
                content={"error": "Internal server error", "message": str(e)}
            )