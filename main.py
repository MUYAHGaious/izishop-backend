from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session
from database.connection import create_tables, get_db
from routers import auth, admin, shop, product, rating, notification, order, shop_owner, notifications
# Temporarily comment out upload router if it's causing issues
# from routers import upload
from routers.auth import get_current_user
from schemas.user import UserResponse
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

# Simple health check endpoint
@app.get("/api/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "message": "Backend is running"}

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
    
    today = date.today()
    
    # Get today's orders (when Order model exists)
    try:
        today_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) == today
        ).count()
        
        today_sales = db.query(func.sum(Order.total_amount)).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) == today
        ).scalar() or 0.0
    except:
        # Order table doesn't exist yet
        today_orders = 0
        today_sales = 0.0
    
    # Calculate yesterday's data for comparison
    from datetime import timedelta
    yesterday = today - timedelta(days=1)
    
    try:
        yesterday_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) == yesterday
        ).count()
        
        yesterday_sales = db.query(func.sum(Order.total_amount)).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) == yesterday
        ).scalar() or 0.0
    except:
        yesterday_orders = 0
        yesterday_sales = 0.0
    
    # Calculate percentage changes
    def calculate_change(current, previous):
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)
    
    sales_change = calculate_change(today_sales, yesterday_sales)
    orders_change = calculate_change(today_orders, yesterday_orders)
    
    # Calculate this month vs last month for more metrics
    from datetime import timedelta
    import calendar
    
    # Get this month and last month data
    today_date = datetime.now().date()
    first_day_this_month = today_date.replace(day=1)
    last_month = first_day_this_month - timedelta(days=1)
    first_day_last_month = last_month.replace(day=1)
    
    try:
        # This month's data
        this_month_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) >= first_day_this_month
        ).count()
        
        this_month_sales = db.query(func.sum(Order.total_amount)).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) >= first_day_this_month
        ).scalar() or 0.0
        
        # Last month's data
        last_month_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) >= first_day_last_month,
            func.date(Order.created_at) < first_day_this_month
        ).count()
        
        last_month_sales = db.query(func.sum(Order.total_amount)).filter(
            Order.shop_id == shop.id,
            func.date(Order.created_at) >= first_day_last_month,
            func.date(Order.created_at) < first_day_this_month
        ).scalar() or 0.0
        
        # Calculate monthly changes
        monthly_sales_change = calculate_change(this_month_sales, last_month_sales)
        monthly_orders_change = calculate_change(this_month_orders, last_month_orders)
        
        # Calculate trend prediction using simple linear regression
        weekly_sales = []
        for week in range(4):  # Last 4 weeks
            week_start = today_date - timedelta(weeks=week+1)
            week_end = today_date - timedelta(weeks=week)
            
            week_sales = db.query(func.sum(Order.total_amount)).filter(
                Order.shop_id == shop.id,
                func.date(Order.created_at) >= week_start,
                func.date(Order.created_at) < week_end
            ).scalar() or 0.0
            
            weekly_sales.append(float(week_sales))
        
        # Simple trend calculation (average of last 2 weeks vs average of first 2 weeks)
        recent_avg = (weekly_sales[0] + weekly_sales[1]) / 2 if len(weekly_sales) >= 2 else 0
        older_avg = (weekly_sales[2] + weekly_sales[3]) / 2 if len(weekly_sales) >= 4 else 0
        trend_direction = "up" if recent_avg > older_avg else "down" if recent_avg < older_avg else "stable"
        
    except:
        this_month_sales = 0.0
        this_month_orders = 0
        monthly_sales_change = 0.0
        monthly_orders_change = 0.0
        trend_direction = "stable"
    
    # Get product stats
    try:
        total_products = db.query(Product).filter(Product.seller_id == current_user.id).count()
        active_products = db.query(Product).filter(
            Product.seller_id == current_user.id,
            Product.is_active == True
        ).count()
        low_stock_products = db.query(Product).filter(
            Product.seller_id == current_user.id,
            Product.stock_quantity <= 10,  # Assuming low stock threshold of 10
            Product.is_active == True
        ).count()
    except:
        total_products = 0
        active_products = 0
        low_stock_products = 0

    return {
        "today_sales": float(today_sales),
        "today_orders": today_orders,
        "visitors": 0,  # Will need analytics table for this
        "conversion_rate": 0.0,
        "sales_change": sales_change,
        "orders_change": orders_change,
        "sales_change_type": "increase" if sales_change >= 0 else "decrease",
        "orders_change_type": "increase" if orders_change >= 0 else "decrease",
        "this_month_sales": float(this_month_sales),
        "this_month_orders": this_month_orders,
        "last_month_sales": float(last_month_sales),
        "last_month_orders": last_month_orders,
        "monthly_sales_change": monthly_sales_change,
        "monthly_orders_change": monthly_orders_change,
        "trend_direction": trend_direction,
        "total_products": total_products,
        "active_products": active_products,
        "low_stock_products": low_stock_products
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
app.include_router(rating.router, tags=["Ratings"])
app.include_router(notification.router, prefix="/api/notifications", tags=["Notifications"])
app.include_router(notifications.router, prefix="/api/ai-notifications", tags=["AI Notifications"])
app.include_router(order.router, prefix="/api/orders", tags=["Orders"])
app.include_router(shop_owner.router, prefix="/api/shop-owner", tags=["Shop Owner"])
# Temporarily comment out upload router
# app.include_router(upload.router, prefix="/api/uploads", tags=["File Uploads"])

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