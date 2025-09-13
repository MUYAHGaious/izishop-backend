#!/usr/bin/env python3
"""
Run script for Izishop Backend
This file serves as the entry point to start the FastAPI server
"""

import uvicorn
from main import app

if __name__ == "__main__":
    print("Starting Izishop Backend Server...")
    print("Server will be available at: http://localhost:8000")
    print("API Documentation at: http://localhost:8000/docs")
    print("Health check at: http://localhost:8000/health")
    print("=" * 50)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
