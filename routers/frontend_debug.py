"""
Frontend Debug Logger Endpoint
Receives logs from frontend and saves them to debug-logs/frontend/
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
import json
import os

router = APIRouter(prefix="/api/debug", tags=["debug"])

# Create frontend logs directory if it doesn't exist
FRONTEND_LOGS_DIR = os.path.join("debug-logs", "frontend")
os.makedirs(FRONTEND_LOGS_DIR, exist_ok=True)

class LogEntry(BaseModel):
    timestamp: str
    level: str
    message: str
    data: Optional[Any] = None
    url: str
    userAgent: str

class FrontendLogRequest(BaseModel):
    logs: List[LogEntry]
    page: str

@router.post("/log")
async def receive_frontend_logs(request: FrontendLogRequest):
    """
    Receive logs from frontend and save to file
    """
    try:
        # Create filename with timestamp
        now = datetime.now()
        filename = f"frontend-{now.strftime('%Y%m%d')}.log"
        filepath = os.path.join(FRONTEND_LOGS_DIR, filename)

        # Write logs to file
        with open(filepath, 'a', encoding='utf-8') as f:
            for log in request.logs:
                log_line = {
                    'timestamp': log.timestamp,
                    'level': log.level,
                    'page': request.page,
                    'message': log.message,
                    'data': log.data,
                    'url': log.url
                }
                f.write(json.dumps(log_line) + '\n')

        return {"status": "success", "logged": len(request.logs)}

    except Exception as e:
        # Don't fail - logging should never break the app
        print(f"Failed to write frontend logs: {e}")
        return {"status": "error", "message": str(e)}
