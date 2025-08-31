from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from routers.auth import auth_router
from routers.user import user_router
from core.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("🚀 User Service starting up...")
    logger.info(f"📊 Environment: {settings.ENVIRONMENT}")
    logger.info(f"🔐 Security Level: {settings.SECURITY_LEVEL}")
    
    yield
    
    # Shutdown
    logger.info("🛑 User Service shutting down...")

# Create FastAPI application
app = FastAPI(
    title="Izishop User Service",
    description="User authentication and management microservice for Izishop",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware for security
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.ALLOWED_HOSTS
)

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for the User Service."""
    return {
        "service": "User Service",
        "status": "healthy",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }

# Service information endpoint
@app.get("/info", tags=["Service Info"])
async def service_info():
    """Get service information and capabilities."""
    return {
        "service": "User Service",
        "description": "User authentication and management microservice",
        "version": "1.0.0",
        "capabilities": [
            "User Registration",
            "User Authentication",
            "JWT Token Management",
            "Profile Management",
            "Password Management",
            "User Search and Filtering",
            "Admin Operations",
            "Email Verification"
        ],
        "endpoints": {
            "auth": "/auth",
            "users": "/users",
            "health": "/health",
            "docs": "/docs"
        }
    }

# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint for the User Service."""
    return {
        "message": "Welcome to Izishop User Service",
        "service": "User Service",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {str(exc)}")
    return HTTPException(
        status_code=500,
        detail="Internal server error"
    )

if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting User Service...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,  # Different port from main backend
        reload=True if settings.ENVIRONMENT == "development" else False,
        log_level="info"
    ) 