from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from database.connection import create_tables
from routers import auth, admin, shop, product
import logging
from pydantic import ValidationError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Izishop Backend API",
    description="Backend API for Izishop e-commerce platform",
    version="1.0.0"
)

# Global exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed error messages."""
    logger.error(f"Validation error on {request.method} {request.url}: {exc}")
    
    error_details = []
    for error in exc.errors():
        field = '.'.join(str(x) for x in error['loc'])
        message = error['msg']
        error_details.append({
            "field": field,
            "message": message,
            "type": error['type']
        })
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation failed",
            "errors": error_details
        }
    )

# Global exception handler for general HTTP exceptions
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with logging."""
    logger.error(f"HTTP exception on {request.method} {request.url}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Global exception handler for unexpected errors
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(f"Unexpected error on {request.method} {request.url}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again."}
    )

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:4028"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(shop.router, prefix="/api/shops", tags=["Shops"])
app.include_router(product.router, prefix="/api/products", tags=["Products"])

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    try:
        logger.info("Starting up Izishop Backend API...")
        create_tables()
        logger.info("Database tables created successfully")
        logger.info("Izishop Backend API started successfully")
    except Exception as e:
        logger.error(f"Failed to start application: {str(e)}")
        raise

@app.get("/")
def root():
    """Root endpoint for API health check."""
    return {
        "message": "Welcome to Izishop Backend API",
        "status": "healthy",
        "version": "1.0.0"
    }

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T00:00:00Z"
    } 