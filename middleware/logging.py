"""
Enhanced logging middleware for production
"""
import time
import logging
import json
from fastapi import Request, Response
from typing import Callable
import uuid


logger = logging.getLogger(__name__)


class LoggingMiddleware:
    """Enhanced logging middleware for production monitoring"""
    
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        
        # Generate request ID
        request_id = str(uuid.uuid4())
        
        # Start time
        start_time = time.time()
        
        # Get client info
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "")
        
        # Log request
        logger.info(
            f"Request started: {request.method} {request.url} - "
            f"ID: {request_id} - IP: {client_ip}"
        )

        # Prepare response data
        response_data = {"status_code": 0, "body": b""}

        async def send_with_logging(message):
            nonlocal response_data
            
            if message["type"] == "http.response.start":
                response_data["status_code"] = message["status"]
                
                # Add request ID to response headers
                headers = dict(message.get("headers", []))
                headers[b"x-request-id"] = request_id.encode()
                message["headers"] = list(headers.items())
            
            elif message["type"] == "http.response.body":
                response_data["body"] += message.get("body", b"")
            
            await send(message)

        try:
            await self.app(scope, receive, send_with_logging)
            
            # Calculate duration
            duration = time.time() - start_time
            
            # Determine log level based on status code and duration
            status_code = response_data["status_code"]
            log_level = logging.INFO
            
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING
            elif duration > 5.0:  # Slow requests
                log_level = logging.WARNING
            
            # Log response
            log_data = {
                "request_id": request_id,
                "method": request.method,
                "url": str(request.url),
                "status_code": status_code,
                "duration": round(duration, 3),
                "client_ip": client_ip,
                "user_agent": user_agent[:100],  # Truncate long user agents
                "response_size": len(response_data["body"])
            }
            
            # Add query parameters for GET requests
            if request.method == "GET" and request.query_params:
                log_data["query_params"] = dict(request.query_params)
            
            logger.log(
                log_level,
                f"Request completed: {request.method} {request.url} - "
                f"Status: {status_code} - Duration: {duration:.3f}s"
            )
            
            # Log detailed data as JSON for log aggregation
            logger.info(f"REQUEST_DATA: {json.dumps(log_data)}")
            
        except Exception as e:
            # Calculate duration for error case
            duration = time.time() - start_time
            
            logger.error(
                f"Request failed: {request.method} {request.url} - "
                f"ID: {request_id} - Duration: {duration:.3f}s - Error: {str(e)}",
                exc_info=True
            )
            
            # Re-raise the exception
            raise


class APIMetricsMiddleware:
    """Collect API metrics for monitoring"""
    
    def __init__(self, app):
        self.app = app
        self.metrics = {
            "requests_total": 0,
            "requests_by_status": {},
            "requests_by_endpoint": {},
            "average_response_time": 0,
            "total_response_time": 0
        }

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        start_time = time.time()
        
        response_data = {"status_code": 0}

        async def send_with_metrics(message):
            nonlocal response_data
            
            if message["type"] == "http.response.start":
                response_data["status_code"] = message["status"]
            
            await send(message)

        try:
            await self.app(scope, receive, send_with_metrics)
            
            # Update metrics
            duration = time.time() - start_time
            status_code = response_data["status_code"]
            endpoint = f"{request.method} {request.url.path}"
            
            self.metrics["requests_total"] += 1
            self.metrics["total_response_time"] += duration
            self.metrics["average_response_time"] = (
                self.metrics["total_response_time"] / self.metrics["requests_total"]
            )
            
            # Update status code counts
            status_range = f"{status_code // 100}xx"
            self.metrics["requests_by_status"][status_range] = (
                self.metrics["requests_by_status"].get(status_range, 0) + 1
            )
            
            # Update endpoint counts
            self.metrics["requests_by_endpoint"][endpoint] = (
                self.metrics["requests_by_endpoint"].get(endpoint, 0) + 1
            )
            
            # Log metrics every 100 requests
            if self.metrics["requests_total"] % 100 == 0:
                logger.info(f"API_METRICS: {json.dumps(self.metrics)}")
            
        except Exception as e:
            logger.error(f"Metrics collection error: {str(e)}")
            raise