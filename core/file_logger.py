"""
Backend File Logger - Saves all FastAPI logs to organized files
Captures requests, responses, errors, and system events automatically
"""
import logging
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
import sys

class IzishopFileLogger:
    def __init__(self, log_dir: str = "debug-logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create session ID for this server run
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Setup different log files
        self.setup_loggers()
        
    def setup_loggers(self):
        """Setup different loggers for different types of logs"""
        
        # Main application logger
        self.app_logger = logging.getLogger("izishop_app")
        self.app_logger.setLevel(logging.DEBUG)
        
        # API requests logger
        self.api_logger = logging.getLogger("izishop_api")
        self.api_logger.setLevel(logging.DEBUG)
        
        # Error logger
        self.error_logger = logging.getLogger("izishop_errors")
        self.error_logger.setLevel(logging.ERROR)
        
        # Database logger
        self.db_logger = logging.getLogger("izishop_database")
        self.db_logger.setLevel(logging.DEBUG)
        
        # Create file handlers
        today = datetime.now().strftime("%Y-%m-%d")
        
        handlers = [
            {
                "logger": self.app_logger,
                "filename": f"app-{today}-{self.session_id}.log",
                "level": logging.DEBUG
            },
            {
                "logger": self.api_logger,
                "filename": f"api-requests-{today}-{self.session_id}.log",
                "level": logging.DEBUG
            },
            {
                "logger": self.error_logger,
                "filename": f"errors-{today}-{self.session_id}.log",
                "level": logging.ERROR
            },
            {
                "logger": self.db_logger,
                "filename": f"database-{today}-{self.session_id}.log",
                "level": logging.DEBUG
            }
        ]
        
        # Setup file handlers with rotation
        for handler_config in handlers:
            file_handler = logging.FileHandler(
                self.log_dir / handler_config["filename"],
                mode='a',
                encoding='utf-8',
                errors='replace'  # Replace invalid characters instead of failing
            )
            
            # Create detailed formatter
            formatter = logging.Formatter(
                '[%(asctime)s] %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(handler_config["level"])
            
            # Add handler to logger
            handler_config["logger"].addHandler(file_handler)
            
            # Also add console handler for errors
            if handler_config["level"] >= logging.ERROR:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                console_handler.setLevel(logging.ERROR)
                handler_config["logger"].addHandler(console_handler)
    
    def _sanitize_data(self, data: Any) -> Any:
        """Sanitize data to prevent encoding corruption in logs"""
        if isinstance(data, str):
            try:
                # Ensure string is properly encoded as UTF-8
                return data.encode('utf-8', errors='replace').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                # Replace problematic characters
                return data.encode('utf-8', errors='replace').decode('utf-8')
        elif isinstance(data, dict):
            return {k: self._sanitize_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        else:
            return str(data) if data is not None else None

    def log_api_request(self, method: str, url: str, headers: Dict[str, Any] = None,
                       body: Any = None, status_code: int = None,
                       response_time: float = None, client_ip: str = None):
        """Log API request details"""

        # Mask sensitive headers to prevent JWT tokens and secrets from being logged
        sanitized_headers = None
        if headers:
            sanitized_headers = {}
            sensitive_headers = ['authorization', 'cookie', 'x-api-key', 'x-auth-token', 'authentication']

            for key, value in headers.items():
                key_lower = key.lower()
                if any(sensitive in key_lower for sensitive in sensitive_headers):
                    # Mask sensitive headers - only show first/last few characters
                    if len(str(value)) > 10:
                        sanitized_headers[key] = f"{str(value)[:8]}...{str(value)[-4:]}"
                    else:
                        sanitized_headers[key] = "[MASKED]"
                else:
                    sanitized_headers[key] = self._sanitize_data(value)

        log_data = {
            "timestamp": datetime.now().isoformat(),
            "method": self._sanitize_data(method),
            "url": self._sanitize_data(url),
            "client_ip": self._sanitize_data(client_ip),
            "status_code": status_code,
            "response_time_ms": round(response_time * 1000, 2) if response_time else None,
            "headers": sanitized_headers,
            "body_size": len(str(body)) if body else 0
        }

        # Log as JSON for easy parsing with proper encoding
        try:
            json_str = json.dumps(log_data, separators=(',', ':'), ensure_ascii=False)
            self.api_logger.info(json_str)
        except (TypeError, ValueError, UnicodeEncodeError) as e:
            # Fallback logging if JSON serialization fails
            self.api_logger.info(f"LOG_ERROR: Failed to serialize log data: {str(e)}")
            self.api_logger.info(f"LOG_DATA: {str(log_data)}")
    
    def log_error(self, error: Exception, context: str = None, extra_data: Dict[str, Any] = None):
        """Log errors with context"""
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": self._sanitize_data(str(error)),
            "context": self._sanitize_data(context),
            "extra_data": self._sanitize_data(extra_data)
        }
        
        try:
            json_str = json.dumps(error_data, separators=(',', ':'), ensure_ascii=False)
            self.error_logger.error(json_str)
        except (TypeError, ValueError, UnicodeEncodeError) as e:
            # Fallback logging if JSON serialization fails
            self.error_logger.error(f"LOG_ERROR: Failed to serialize error data: {str(e)}")
            self.error_logger.error(f"ERROR_DATA: {str(error_data)}")
    
    def log_database_query(self, query: str, params: Any = None, duration: float = None, 
                          result_count: int = None):
        """Log database queries"""
        query_data = {
            "timestamp": datetime.now().isoformat(),
            "query": self._sanitize_data(query[:500] + "..." if len(query) > 500 else query),  # Truncate long queries
            "params": self._sanitize_data(str(params) if params else None),
            "duration_ms": round(duration * 1000, 2) if duration else None,
            "result_count": result_count
        }
        
        try:
            json_str = json.dumps(query_data, separators=(',', ':'), ensure_ascii=False)
            self.db_logger.debug(json_str)
        except (TypeError, ValueError, UnicodeEncodeError) as e:
            # Fallback logging if JSON serialization fails
            self.db_logger.debug(f"LOG_ERROR: Failed to serialize query data: {str(e)}")
            self.db_logger.debug(f"QUERY_DATA: {str(query_data)}")
    
    def log_app_event(self, event: str, details: Dict[str, Any] = None):
        """Log general application events"""
        event_data = {
            "timestamp": datetime.now().isoformat(),
            "event": self._sanitize_data(event),
            "details": self._sanitize_data(details)
        }
        
        try:
            json_str = json.dumps(event_data, separators=(',', ':'), ensure_ascii=False)
            self.app_logger.info(json_str)
        except (TypeError, ValueError, UnicodeEncodeError) as e:
            # Fallback logging if JSON serialization fails
            self.app_logger.info(f"LOG_ERROR: Failed to serialize event data: {str(e)}")
            self.app_logger.info(f"EVENT_DATA: {str(event_data)}")
    
    def log_startup(self):
        """Log application startup"""
        startup_info = {
            "session_id": self.session_id,
            "startup_time": datetime.now().isoformat(),
            "python_version": sys.version,
            "log_directory": str(self.log_dir.absolute())
        }
        
        self.app_logger.info("=" * 80)
        self.app_logger.info("IZISHOP BACKEND STARTED")
        try:
            startup_json = json.dumps(startup_info, indent=2, ensure_ascii=False)
            self.app_logger.info(startup_json)
        except (TypeError, ValueError, UnicodeEncodeError) as e:
            self.app_logger.info(f"LOG_ERROR: Failed to serialize startup info: {str(e)}")
            self.app_logger.info(f"STARTUP_INFO: {str(startup_info)}")
        self.app_logger.info("=" * 80)
        
        print(f"IziShop Backend Logging Started")
        print(f"Logs saved to: {self.log_dir.absolute()}")
        print(f"Session ID: {self.session_id}")

# Global logger instance
file_logger = IzishopFileLogger()# Comment to trigger reload
