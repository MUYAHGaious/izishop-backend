"""
Debug Router - Handles frontend console logs and debug information
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import os
from datetime import datetime
from pathlib import Path
from core.file_logger import file_logger

router = APIRouter(prefix="/api/debug", tags=["debug"])

class LogEntry(BaseModel):
    timestamp: str
    timeStr: str
    level: str
    page: str
    message: str
    sessionId: str
    raw: str

class FrontendLogsPayload(BaseModel):
    sessionId: str
    logs: List[LogEntry]
    timestamp: str
    immediate: Optional[bool] = False

@router.post("/frontend-logs")
async def receive_frontend_logs(payload: FrontendLogsPayload, request: Request):
    """Receive and save frontend console logs"""
    
    try:
        # Create frontend logs directory
        frontend_logs_dir = Path("debug-logs") / "frontend"
        frontend_logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename based on session and date
        today = datetime.now().strftime("%Y-%m-%d")
        session_short = payload.sessionId.split('_')[-1]  # Get the random part
        filename = f"frontend-console-{today}-{session_short}.log"
        log_file_path = frontend_logs_dir / filename
        
        # Prepare log content
        log_lines = []
        for log_entry in payload.logs:
            log_lines.append(log_entry.raw)
        
        log_content = '\n'.join(log_lines) + '\n'
        
        # Append to file (create if doesn't exist)
        with open(log_file_path, 'a', encoding='utf-8') as f:
            f.write(log_content)
        
        # Also log the event in our backend logger
        file_logger.log_app_event(
            event="frontend_logs_received",
            details={
                "session_id": payload.sessionId,
                "log_count": len(payload.logs),
                "immediate": payload.immediate,
                "file_path": str(log_file_path),
                "client_ip": request.client.host if request.client else "unknown"
            }
        )
        
        return {
            "status": "success",
            "message": f"Saved {len(payload.logs)} frontend logs",
            "file_path": str(log_file_path),
            "session_id": payload.sessionId
        }
        
    except Exception as e:
        file_logger.log_error(
            error=e,
            context="frontend_logs_endpoint",
            extra_data={
                "session_id": payload.sessionId,
                "log_count": len(payload.logs)
            }
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save frontend logs: {str(e)}"
        )

@router.get("/frontend-logs/{session_id}")
async def get_frontend_logs(session_id: str):
    """Retrieve frontend logs for a specific session"""
    
    try:
        frontend_logs_dir = Path("debug-logs") / "frontend"
        
        # Find log files for this session
        session_short = session_id.split('_')[-1] if '_' in session_id else session_id
        log_files = list(frontend_logs_dir.glob(f"*{session_short}.log"))
        
        if not log_files:
            raise HTTPException(
                status_code=404,
                detail=f"No log files found for session: {session_id}"
            )
        
        # Read the most recent log file
        latest_file = max(log_files, key=lambda f: f.stat().st_mtime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        return {
            "session_id": session_id,
            "file_path": str(latest_file),
            "content": content,
            "file_size": latest_file.stat().st_size,
            "last_modified": datetime.fromtimestamp(latest_file.stat().st_mtime).isoformat()
        }
        
    except Exception as e:
        file_logger.log_error(
            error=e,
            context="get_frontend_logs",
            extra_data={"session_id": session_id}
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve frontend logs: {str(e)}"
        )

@router.get("/logs/list")
async def list_debug_logs():
    """List all available debug log files"""
    
    try:
        debug_logs_dir = Path("debug-logs")
        
        if not debug_logs_dir.exists():
            return {"logs": []}
        
        log_files = []
        
        # Scan for all log files
        for log_file in debug_logs_dir.rglob("*.log"):
            file_info = {
                "name": log_file.name,
                "path": str(log_file.relative_to(debug_logs_dir)),
                "size": log_file.stat().st_size,
                "modified": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(),
                "type": "frontend" if "frontend" in str(log_file) else "backend"
            }
            log_files.append(file_info)
        
        # Sort by modification time (newest first)
        log_files.sort(key=lambda x: x["modified"], reverse=True)
        
        return {
            "logs": log_files,
            "total_count": len(log_files),
            "directory": str(debug_logs_dir.absolute())
        }
        
    except Exception as e:
        file_logger.log_error(
            error=e,
            context="list_debug_logs"
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list debug logs: {str(e)}"
        )

@router.get("/status")
async def debug_status():
    """Get current debug system status"""
    
    try:
        debug_logs_dir = Path("debug-logs")
        
        # Count log files
        frontend_logs = len(list((debug_logs_dir / "frontend").glob("*.log"))) if (debug_logs_dir / "frontend").exists() else 0
        backend_logs = len(list(debug_logs_dir.glob("*.log")))
        
        return {
            "status": "active",
            "debug_directory": str(debug_logs_dir.absolute()),
            "frontend_log_files": frontend_logs,
            "backend_log_files": backend_logs,
            "total_files": frontend_logs + backend_logs,
            "session_timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        file_logger.log_error(
            error=e,
            context="debug_status"
        )
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get debug status: {str(e)}"
        )