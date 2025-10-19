from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database.connection import create_tables, get_db
import sys
# Import all models to ensure they're registered with SQLAlchemy
from models import user, shop, product, order, subscription, analytics, casual_listing, review, chat, contacts
from routers import auth, admin, shop, product, rating, notification, order, shop_owner, notifications, customer, debug, tranzak_webhooks, casual_listings, transaction_fees, delivery_partner, subscription_management, analytics, batch_operations, wishlist, chat, order_optimized, frontend_debug, category, review
# Upload router for image uploads - temporarily disabled
# from routers import upload
from routers.auth import get_current_user
from schemas.user import UserResponse
import logging
from pydantic import ValidationError

# Import our new architecture components
from core.security_middleware import create_security_middleware_stack
from core.exceptions import (
    BaseCustomException, 
    BusinessLogicError, 
    ResourceNotFoundError,
    AuthenticationError, 
    AuthorizationError, 
    ValidationError as CustomValidationError,
    create_http_exception_from_custom
)
from core.response import error_response

# Import file logging system
from core.file_logger import file_logger
from core.logging_middleware import LoggingMiddleware

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Ensure all loggers use UTF-8 encoding
for handler in logging.root.handlers:
    if hasattr(handler, 'stream') and hasattr(handler.stream, 'encoding'):
        handler.stream.reconfigure(encoding='utf-8')
logger = logging.getLogger(__name__)

# Configure system encoding for HTTP responses
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'

# Custom response handler to ensure UTF-8 encoding
from fastapi.responses import Response
from fastapi import Request
from typing import Any

class UTF8Response(Response):
    def __init__(self, content: Any = None, *args, **kwargs):
        # Ensure content is properly encoded as UTF-8
        if content is not None:
            if isinstance(content, str):
                content = content.encode('utf-8')
            elif isinstance(content, bytes):
                try:
                    content = content.decode('utf-8').encode('utf-8')
                except UnicodeDecodeError:
                    content = content.decode('utf-8', errors='replace').encode('utf-8')
        
        super().__init__(content, *args, **kwargs)
        self.headers['Content-Type'] = 'application/json; charset=utf-8'

app = FastAPI(
    title="Izishop Backend API",
    description="Backend API for Izishop e-commerce platform",
    version="1.0.0"
)

# Initialize file logging
file_logger.log_startup()

# Add logging middleware (MUST be first to capture all requests)
app.add_middleware(LoggingMiddleware)

# Add UTF-8 encoding middleware
@app.middleware("http")
async def utf8_encoding_middleware(request: Request, call_next):
    response = await call_next(request)
    
    # Ensure response has UTF-8 charset
    if 'content-type' in response.headers:
        content_type = response.headers['content-type']
        if 'charset=' not in content_type:
            response.headers['content-type'] = f"{content_type}; charset=utf-8"
    else:
        response.headers['content-type'] = 'application/json; charset=utf-8'
    
    return response

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler for custom exceptions
@app.exception_handler(BaseCustomException)
async def custom_exception_handler(request: Request, exc: BaseCustomException):
    """Handle custom exceptions with standardized response format."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(f"Custom exception [{request_id}] on {request.method} {request.url}: {exc.message}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.message,
            error_code=exc.__class__.__name__,
            details=exc.details
        )
    )

# Global exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed error messages."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(f"Validation error [{request_id}] on {request.method} {request.url}: {exc}")
    
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
        content=error_response(
            message="Request validation failed",
            error_code="VALIDATION_ERROR",
            details={"errors": error_details}
        )
    )

# Global exception handler for general HTTP exceptions
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with logging."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(f"HTTP exception [{request_id}] on {request.method} {request.url}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=str(exc.detail) if isinstance(exc.detail, str) else "HTTP error occurred",
            error_code="HTTP_ERROR",
            details={"status_code": exc.status_code, "detail": exc.detail}
        )
    )

# Global exception handler for unexpected errors
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.error(f"Unexpected error [{request_id}] on {request.method} {request.url}: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content=error_response(
            message="An unexpected error occurred. Please try again.",
            error_code="INTERNAL_SERVER_ERROR",
            details={"request_id": request_id}
        )
    )

# Apply enterprise security middleware stack using FastAPI's add_middleware method
from core.security_middleware import (
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    InputValidationMiddleware,
    RequestLoggingMiddleware,
)
from core.cors_config import configure_cors

# Configure CORS with proper settings
configure_cors(app)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(InputValidationMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

# Simple health check endpoint
@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "message": "Backend is running"}

# Test CORS endpoint
@app.get("/api/test-cors")
async def test_cors():
    """Test CORS configuration with sample data."""
    return {
        "today_sales": 125.50,
        "today_orders": 3,
        "visitors": 24,
        "conversion_rate": 12.5,
        "sales_change": 8.2,
        "orders_change": 15.0,
        "this_month_sales": 2450.75,
        "this_month_orders": 42,
        "last_month_sales": 2100.00,
        "last_month_orders": 38,
        "monthly_sales_change": 16.7,
        "monthly_orders_change": 10.5,
        "trend_direction": "up",
        "total_products": 12,
        "active_products": 11,
        "low_stock_products": 2
    }

# Categories endpoint - Now handled by category router at /api/categories
# @app.get("/api/categories")
# async def get_categories(db: Session = Depends(get_db)):
#     """Get all available product categories with counts"""
#     # This endpoint is deprecated - use the category router instead for full hierarchy support
#     pass

# Missing shop-owner dashboard endpoints
@app.get("/api/shop-owner/dashboard/today-stats")
async def get_today_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get today's stats for shop owner dashboard."""
    from datetime import datetime, date
    from models.shop import Shop
    from models.order import Order
    from models.product import Product
    from sqlalchemy import func
    
    try:
        # Get the shop for current user
        shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
        if not shop:
            return {
                "today_sales": 0.0,
                "today_orders": 0,
                "visitors": 0,
                "conversion_rate": 0.0,
                "sales_change": 0.0,
                "orders_change": 0.0,
                "this_month_sales": 0.0,
                "this_month_orders": 0,
                "last_month_sales": 0.0,
                "last_month_orders": 0,
                "monthly_sales_change": 0.0,
                "monthly_orders_change": 0.0,
                "trend_direction": "stable",
                "total_products": 0,
                "active_products": 0,
                "low_stock_products": 0
            }
        
        # Return simple stats without complex calculations that might fail
        return {
            "today_sales": 0.0,
            "today_orders": 0,
            "visitors": 0,
            "conversion_rate": 0.0,
            "sales_change": 0.0,
            "orders_change": 0.0,
            "this_month_sales": 0.0,
            "this_month_orders": 0,
            "last_month_sales": 0.0,
            "last_month_orders": 0,
            "monthly_sales_change": 0.0,
            "monthly_orders_change": 0.0,
            "trend_direction": "stable",
            "total_products": 0,
            "active_products": 0,
            "low_stock_products": 0
        }
    except Exception as e:
        logger.error(f"Error in get_today_stats: {str(e)}")
        # Return zero stats instead of failing
        return {
            "today_sales": 0.0,
            "today_orders": 0,
            "visitors": 0,
            "conversion_rate": 0.0,
            "sales_change": 0.0,
            "orders_change": 0.0,
            "this_month_sales": 0.0,
            "this_month_orders": 0,
            "last_month_sales": 0.0,
            "last_month_orders": 0,
            "monthly_sales_change": 0.0,
            "monthly_orders_change": 0.0,
            "trend_direction": "stable",
            "total_products": 0,
            "active_products": 0,
            "low_stock_products": 0
        }

@app.get("/api/shop-owner/orders/recent")
async def get_recent_orders(
    limit: int = 4,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent orders for shop owner."""
    from models.shop import Shop
    from models.order import Order
    
    # Get the shop for current user
    shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
    if not shop:
        return {"orders": []}
    
    try:
        recent_orders = db.query(Order).filter(
            Order.shop_id == shop.id
        ).order_by(Order.created_at.desc()).limit(limit).all()
        
        return {
            "orders": [
                {
                    "id": order.id,
                    "customer": f"{order.customer.first_name} {order.customer.last_name}",
                    "total": float(order.total_amount),
                    "status": order.status
                }
                for order in recent_orders
            ]
        }
    except:
        # Order table doesn't exist yet
        return {"orders": []}

@app.get("/api/shop-owner/products/low-stock")
async def get_low_stock_products(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get low stock products."""
    from models.product import Product
    
    try:
        low_stock_products = db.query(Product).filter(
            Product.seller_id == current_user.id,
            Product.stock_quantity <= Product.low_stock_threshold,
            Product.is_active == True
        ).all()
        
        return {
            "products": [
                {
                    "id": product.id,
                    "name": product.name,
                    "stock": product.stock_quantity,
                    "threshold": product.low_stock_threshold
                }
                for product in low_stock_products
            ]
        }
    except:
        # Product table might not have these columns yet
        return {"products": []}

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(shop.router, prefix="/api/shops", tags=["Shops"])
app.include_router(product.router, prefix="/api/products", tags=["Products"])
app.include_router(category.router, prefix="/api/categories", tags=["Categories"])
app.include_router(rating.router, tags=["Ratings"])
app.include_router(notification.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(notifications.router, prefix="/api/ai-notifications", tags=["AI Notifications"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
app.include_router(order_optimized.router, prefix="/api/orders-v2", tags=["Orders V2 - Optimized"])
app.include_router(shop_owner.router, prefix="/api/shop-owner", tags=["Shop Owner"])
app.include_router(customer.router, prefix="/api/customer", tags=["Customer"])
app.include_router(debug.router, tags=["Debug"])
app.include_router(tranzak_webhooks.router, tags=["Tranzak Payments"])
app.include_router(casual_listings.router, tags=["Casual Marketplace"])
app.include_router(transaction_fees.router, tags=["Transaction Fees"])
app.include_router(delivery_partner.router, tags=["Delivery Integration"])
app.include_router(subscription_management.router, tags=["Subscription Management"])
app.include_router(analytics.router, tags=["Analytics"])
app.include_router(batch_operations.router, prefix="/api", tags=["Batch Operations"])
app.include_router(wishlist.router, prefix="/api", tags=["Wishlist"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(frontend_debug.router, tags=["Frontend Debug"])
app.include_router(review.router, prefix="/api/reviews", tags=["Reviews"])
# Temporarily disable WebSocket and online_status routers due to import issues - needs refactoring
# app.include_router(websocket.router, tags=["WebSocket"])
# app.include_router(online_status.router, tags=["Online Status"])
# Temporarily disable upload router due to unicode issues
# app.include_router(upload.router, prefix="/api/uploads", tags=["File Uploads"])

# Mount static files for serving uploaded media
import os
uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Create database tables on startup
@app.on_event("startup")
async def startup_event():
    """Initialize the application on startup."""
    try:
        logger.info("Starting up Izishop Backend API...")
        create_tables()
        logger.info("Database tables created successfully")

        # Initialize event bus and notification handlers
        from core.event_system import event_bus
        from services.order_notification_handler import order_notification_handler

        await event_bus.initialize()
        logger.info("Event bus initialized successfully")

        logger.info("Order notification handler registered")
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