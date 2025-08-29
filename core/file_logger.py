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
                encoding='utf-8'
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
    
    def log_api_request(self, method: str, url: str, headers: Dict[str, Any] = None, 
                       body: Any = None, status_code: int = None, 
                       response_time: float = None, client_ip: str = None):
        """Log API request details"""
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "method": method,
            "url": url,
            "client_ip": client_ip,
            "status_code": status_code,
            "response_time_ms": round(response_time * 1000, 2) if response_time else None,
            "headers": dict(headers) if headers else None,
            "body_size": len(str(body)) if body else 0
        }
        
        # Log as JSON for easy parsing
        self.api_logger.info(json.dumps(log_data, separators=(',', ':')))
    
    def log_error(self, error: Exception, context: str = None, extra_data: Dict[str, Any] = None):
        """Log errors with context"""
        error_data = {
            "timestamp": datetime.now().isoformat(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "extra_data": extra_data
        }
        
        self.error_logger.error(json.dumps(error_data, separators=(',', ':')))
    
    def log_database_query(self, query: str, params: Any = None, duration: float = None, 
                          result_count: int = None):
        """Log database queries"""
        query_data = {
            "timestamp": datetime.now().isoformat(),
            "query": query[:500] + "..." if len(query) > 500 else query,  # Truncate long queries
            "params": str(params) if params else None,
            "duration_ms": round(duration * 1000, 2) if duration else None,
            "result_count": result_count
        }
        
        self.db_logger.debug(json.dumps(query_data, separators=(',', ':')))
    
    def log_app_event(self, event: str, details: Dict[str, Any] = None):
        """Log general application events"""
        event_data = {
            "timestamp": datetime.now().isoformat(),
            "event": event,
            "details": details
        }
        
        self.app_logger.info(json.dumps(event_data, separators=(',', ':')))
    
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
        self.app_logger.info(json.dumps(startup_info, indent=2))
        self.app_logger.info("=" * 80)
        
        print(f"IziShop Backend Logging Started")
        print(f"Logs saved to: {self.log_dir.absolute()}")
        print(f"Session ID: {self.session_id}")

# Global logger instance
file_logger = IzishopFileLogger()