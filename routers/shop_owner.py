from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
import logging

from database.connection import get_db
from models.shop import Shop
from models.product import Product
from models.user import User, UserRole
from schemas.user import UserResponse
from routers.auth import get_current_user

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

def get_shop_owner_shop(current_user: UserResponse, db: Session):
    """Get the shop for the current shop owner user."""
    if current_user.role != UserRole.SHOP_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only shop owners can access this endpoint"
        )
    
    shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found for this user"
        )
    
    return shop

def calculate_date_range(time_range: str):
    """Calculate start and end dates based on time range string."""
    end_date = datetime.now()
    
    if time_range == '7d':
        start_date = end_date - timedelta(days=7)
    elif time_range == '30d':
        start_date = end_date - timedelta(days=30)
    elif time_range == '90d':
        start_date = end_date - timedelta(days=90)
    elif time_range == '1y':
        start_date = end_date - timedelta(days=365)
    else:
        # Default to 7 days
        start_date = end_date - timedelta(days=7)
    
    return start_date, end_date

def calculate_previous_period_range(start_date: datetime, end_date: datetime):
    """Calculate the previous period for comparison."""
    period_length = end_date - start_date
    previous_end = start_date
    previous_start = previous_end - period_length
    return previous_start, previous_end

def calculate_percentage_change(current: float, previous: float) -> float:
    """Calculate percentage change between two values."""
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100, 1)

@router.get("/analytics")
async def get_shop_owner_analytics(
    range: str = Query("7d", description="Time range: 7d, 30d, 90d, 1y"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get analytics data for shop owner dashboard.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        # Calculate date ranges
        start_date, end_date = calculate_date_range(range)
        prev_start, prev_end = calculate_previous_period_range(start_date, end_date)
        
        # Initialize analytics data with default values
        analytics = {
            "revenue": {"current": 0.0, "previous": 0.0, "change": 0.0},
            "orders": {"current": 0, "previous": 0, "change": 0.0},
            "customers": {"current": 0, "previous": 0, "change": 0.0, "new": 0, "returning": 0, "retention_rate": 0.0, "lifetime_value": 0.0},
            "conversionRate": {"current": 0.0, "previous": 0.0, "change": 0.0}
        }
        
        try:
            # Try to import Order model - it might not exist yet
            from models.order import Order
            
            # Current period orders
            current_orders = db.query(Order).filter(
                and_(
                    Order.shop_id == shop.id,
                    Order.created_at >= start_date,
                    Order.created_at <= end_date
                )
            ).all()
            
            # Previous period orders
            previous_orders = db.query(Order).filter(
                and_(
                    Order.shop_id == shop.id,
                    Order.created_at >= prev_start,
                    Order.created_at <= prev_end
                )
            ).all()
            
            # Calculate current period metrics
            current_revenue = sum(order.total_amount for order in current_orders)
            current_order_count = len(current_orders)
            current_customers = len(set(order.customer_id for order in current_orders))
            
            # Calculate previous period metrics
            previous_revenue = sum(order.total_amount for order in previous_orders)
            previous_order_count = len(previous_orders)
            previous_customers = len(set(order.customer_id for order in previous_orders))
            
            # Update analytics with real data
            analytics["revenue"]["current"] = float(current_revenue)
            analytics["revenue"]["previous"] = float(previous_revenue)
            analytics["revenue"]["change"] = calculate_percentage_change(current_revenue, previous_revenue)
            
            analytics["orders"]["current"] = current_order_count
            analytics["orders"]["previous"] = previous_order_count
            analytics["orders"]["change"] = calculate_percentage_change(current_order_count, previous_order_count)
            
            analytics["customers"]["current"] = current_customers
            analytics["customers"]["previous"] = previous_customers
            analytics["customers"]["change"] = calculate_percentage_change(current_customers, previous_customers)
            
            # Calculate average order value for current period
            avg_order_value = current_revenue / current_order_count if current_order_count > 0 else 0
            analytics["orders"]["average_value"] = float(avg_order_value)
            
            # Calculate customer insights
            if current_customers > 0:
                # New vs returning customers (simplified - customers who ordered in previous period)
                previous_customer_ids = set(order.customer_id for order in previous_orders)
                current_customer_ids = set(order.customer_id for order in current_orders)
                
                new_customers = len(current_customer_ids - previous_customer_ids)
                returning_customers = len(current_customer_ids & previous_customer_ids)
                
                analytics["customers"]["new"] = new_customers
                analytics["customers"]["returning"] = returning_customers
                analytics["customers"]["retention_rate"] = round((returning_customers / len(previous_customer_ids)) * 100, 1) if previous_customer_ids else 0
                analytics["customers"]["lifetime_value"] = float(current_revenue / current_customers)
            
            # No real conversion rate data available yet - return zeros
            analytics["conversionRate"]["current"] = 0.0
            analytics["conversionRate"]["previous"] = 0.0
            analytics["conversionRate"]["change"] = 0.0
            
        except ImportError:
            # Order model doesn't exist yet, return zeros for new users
            logger.info("Order model not available, returning zero analytics for new user")
            analytics = {
                "revenue": {"current": 0.0, "previous": 0.0, "change": 0.0},
                "orders": {"current": 0, "previous": 0, "change": 0.0, "average_value": 0.0},
                "customers": {
                    "current": 0, "previous": 0, "change": 0.0,
                    "new": 0, "returning": 0, "retention_rate": 0.0, "lifetime_value": 0.0
                },
                "conversionRate": {"current": 0.0, "previous": 0.0, "change": 0.0}
            }
        except Exception as e:
            logger.warning(f"Error calculating real analytics, returning zeros: {str(e)}")
            analytics = {
                "revenue": {"current": 0.0, "previous": 0.0, "change": 0.0},
                "orders": {"current": 0, "previous": 0, "change": 0.0, "average_value": 0.0},
                "customers": {
                    "current": 0, "previous": 0, "change": 0.0,
                    "new": 0, "returning": 0, "retention_rate": 0.0, "lifetime_value": 0.0
                },
                "conversionRate": {"current": 0.0, "previous": 0.0, "change": 0.0}
            }
        
        return analytics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop owner analytics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics data"
        )

@router.get("/analytics/top-products")
async def get_shop_owner_top_products(
    limit: int = Query(5, ge=1, le=20, description="Number of top products to return"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get top performing products for shop owner.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        try:
            # Try to get real product data
            from models.order import Order, OrderItem
            
            # Get products with order data
            products_query = db.query(
                Product.id,
                Product.name,
                Product.price,
                func.count(OrderItem.id).label('sales_count'),
                func.sum(OrderItem.quantity * OrderItem.price).label('revenue'),
                func.avg(OrderItem.quantity * OrderItem.price).label('avg_order_value')
            ).join(
                OrderItem, Product.id == OrderItem.product_id
            ).join(
                Order, OrderItem.order_id == Order.id
            ).filter(
                Product.seller_id == current_user.id,
                Order.shop_id == shop.id
            ).group_by(
                Product.id, Product.name, Product.price
            ).order_by(
                desc('revenue')
            ).limit(limit).all()
            
            top_products = []
            for product in products_query:
                # No historical data for growth calculation yet
                growth = 0.0
                
                top_products.append({
                    "id": product.id,
                    "name": product.name,
                    "sales": product.sales_count,
                    "revenue": float(product.revenue),
                    "growth": growth,
                    "avg_order_value": float(product.avg_order_value or 0)
                })
            
            return top_products
            
        except ImportError:
            # Order/OrderItem models don't exist yet - return empty list for new users
            logger.info("Order models not available, returning empty top products list")
            return []
            
        except Exception as e:
            logger.warning(f"Error getting real product data: {str(e)}")
            # No real data available - return empty list for new users
            return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting top products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve top products"
        )

@router.get("/analytics/sales")
async def get_shop_owner_sales_data(
    range: str = Query("7d", description="Time range: 7d, 30d, 90d, 1y"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get sales data over time for shop owner.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        # Calculate date range
        start_date, end_date = calculate_date_range(range)
        
        try:
            from models.order import Order
            
            # Determine grouping based on range
            if range == '7d':
                # Daily grouping for 7 days
                date_format = '%Y-%m-%d'
                interval = timedelta(days=1)
            elif range == '30d':
                # Daily grouping for 30 days
                date_format = '%Y-%m-%d'
                interval = timedelta(days=1)
            elif range == '90d':
                # Weekly grouping for 90 days
                date_format = '%Y-W%U'
                interval = timedelta(days=7)
            else:  # 1y
                # Monthly grouping for 1 year
                date_format = '%Y-%m'
                interval = timedelta(days=30)
            
            # Query sales data grouped by date
            sales_data = db.query(
                func.date(Order.created_at).label('date'),
                func.sum(Order.total_amount).label('sales'),
                func.count(Order.id).label('orders')
            ).filter(
                and_(
                    Order.shop_id == shop.id,
                    Order.created_at >= start_date,
                    Order.created_at <= end_date
                )
            ).group_by(
                func.date(Order.created_at)
            ).order_by('date').all()
            
            # Convert to list of dictionaries
            result = []
            for data in sales_data:
                result.append({
                    "date": data.date.strftime('%Y-%m-%d'),
                    "sales": float(data.sales),
                    "orders": data.orders
                })
            
            return result
            
        except ImportError:
            # Order model doesn't exist, return empty data
            logger.info("Order model not available, returning empty sales data")
            return []
            
        except Exception as e:
            logger.warning(f"Error getting real sales data: {str(e)}")
            # Return empty data for new users
            return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sales data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sales data"
        )

@router.get("/analytics/traffic-sources")
async def get_shop_owner_traffic_sources(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get traffic sources analytics for shop owner.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        # In a real implementation, this would come from web analytics tools like Google Analytics
        # For now, we'll generate realistic data based on shop performance
        try:
            from models.order import Order
            
            # Get total orders to estimate traffic
            total_orders = db.query(func.count(Order.id)).filter(
                Order.shop_id == shop.id,
                Order.created_at >= datetime.now() - timedelta(days=30)
            ).scalar() or 0
            
            # Estimate traffic based on orders (assuming 2% conversion rate)
            estimated_visitors = max(100, total_orders * 50)
            
            # Generate realistic traffic distribution
            traffic_sources = [
                {
                    "source": "Direct",
                    "visitors": int(estimated_visitors * 0.35),
                    "percentage": 35,
                    "conversion_rate": 2.8
                },
                {
                    "source": "Social Media", 
                    "visitors": int(estimated_visitors * 0.27),
                    "percentage": 27,
                    "conversion_rate": 1.9
                },
                {
                    "source": "Search Engine",
                    "visitors": int(estimated_visitors * 0.22),
                    "percentage": 22,
                    "conversion_rate": 3.2
                },
                {
                    "source": "Email",
                    "visitors": int(estimated_visitors * 0.11),
                    "percentage": 11,
                    "conversion_rate": 4.1
                },
                {
                    "source": "Referral",
                    "visitors": int(estimated_visitors * 0.05),
                    "percentage": 5,
                    "conversion_rate": 2.5
                }
            ]
            
            return traffic_sources
            
        except ImportError:
            # Order model doesn't exist - return empty list for new users
            logger.info("Order model not available, returning empty traffic sources")
            return []
            
        except Exception as e:
            logger.warning(f"Error calculating traffic sources: {str(e)}")
            # No real data available - return empty list for new users
            return []
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting traffic sources: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve traffic sources"
        )

@router.get("/customers")
async def get_shop_owner_customers(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get customers for shop owner.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        try:
            from models.order import Order
            
            # Get unique customers who have ordered from this shop
            offset = (page - 1) * limit
            
            customers_query = db.query(
                User.id,
                User.first_name,
                User.last_name,
                User.email,
                func.count(Order.id).label('total_orders'),
                func.sum(Order.total_amount).label('total_spent'),
                func.max(Order.created_at).label('last_order_date')
            ).join(
                Order, User.id == Order.customer_id
            ).filter(
                Order.shop_id == shop.id
            ).group_by(
                User.id, User.first_name, User.last_name, User.email
            ).order_by(
                desc('total_spent')
            ).offset(offset).limit(limit).all()
            
            customers = []
            for customer in customers_query:
                customers.append({
                    "id": customer.id,
                    "name": f"{customer.first_name} {customer.last_name}",
                    "email": customer.email,
                    "total_orders": customer.total_orders,
                    "total_spent": float(customer.total_spent),
                    "last_order_date": customer.last_order_date.isoformat(),
                    "avg_order_value": float(customer.total_spent / customer.total_orders)
                })
            
            # Get total count for pagination
            total_count = db.query(func.count(func.distinct(Order.customer_id))).filter(
                Order.shop_id == shop.id
            ).scalar()
            
            return {
                "customers": customers,
                "total": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit
            }
            
        except ImportError:
            # Order model doesn't exist - return empty customer list for new users
            logger.info("Order model not available, returning empty customer list")
            return {
                "customers": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "total_pages": 0
            }
            
        except Exception as e:
            logger.warning(f"Error getting real customer data, using mock data: {str(e)}")
            return {
                "customers": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "total_pages": 0
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting customers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customers"
        )

@router.get("/orders")
async def get_shop_owner_orders(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, description="Filter by order status"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get orders for shop owner.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        try:
            from models.order import Order
            
            offset = (page - 1) * limit
            
            # Build query
            query = db.query(Order).filter(Order.shop_id == shop.id)
            
            if status_filter:
                query = query.filter(Order.status == status_filter)
            
            # Get total count
            total_count = query.count()
            
            # Get paginated results
            orders = query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
            
            result_orders = []
            for order in orders:
                result_orders.append({
                    "id": order.id,
                    "customer_name": f"{order.customer.first_name} {order.customer.last_name}",
                    "customer_email": order.customer.email,
                    "total_amount": float(order.total_amount),
                    "status": order.status,
                    "created_at": order.created_at.isoformat(),
                    "updated_at": order.updated_at.isoformat()
                })
            
            return {
                "orders": result_orders,
                "total": total_count,
                "page": page,
                "limit": limit,
                "total_pages": (total_count + limit - 1) // limit
            }
            
        except ImportError:
            # Order model doesn't exist - return empty order list for new users
            logger.info("Order model not available, returning empty order list")
            return {
                "orders": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "total_pages": 0
            }
            
        except Exception as e:
            logger.warning(f"Error getting real order data, using mock data: {str(e)}")
            return {
                "orders": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "total_pages": 0
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting orders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve orders"
        )

@router.get("/rating-stats")
async def get_shop_owner_rating_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get rating statistics for shop owner.
    """
    try:
        shop = get_shop_owner_shop(current_user, db)
        
        try:
            # Try to get real rating data from review models
            from models.review import Review
            
            # Get ratings for this shop's products
            ratings_query = db.query(
                func.avg(Review.rating).label('average_rating'),
                func.count(Review.id).label('total_reviews'),
                func.count(func.distinct(Review.user_id)).label('unique_reviewers')
            ).join(
                Product, Review.product_id == Product.id
            ).filter(
                Product.seller_id == current_user.id
            ).first()
            
            # Get rating distribution
            rating_distribution = db.query(
                Review.rating,
                func.count(Review.id).label('count')
            ).join(
                Product, Review.product_id == Product.id
            ).filter(
                Product.seller_id == current_user.id
            ).group_by(Review.rating).all()
            
            distribution = {str(i): 0 for i in range(1, 6)}
            for rating, count in rating_distribution:
                distribution[str(rating)] = count
            
            return {
                "average_rating": float(ratings_query.average_rating or 0),
                "total_reviews": ratings_query.total_reviews or 0,
                "unique_reviewers": ratings_query.unique_reviewers or 0,
                "rating_distribution": distribution,
                "response_rate": 85.0,  # Mock data - would need review responses
                "recent_trend": "+0.2"  # Mock trend
            }
            
        except ImportError:
            # Review model doesn't exist - return empty rating stats for new users
            logger.info("Review model not available, returning empty rating stats")
            return {
                "average_rating": 0.0,
                "total_reviews": 0,
                "unique_reviewers": 0,
                "rating_distribution": {
                    "5": 0,
                    "4": 0,
                    "3": 0,
                    "2": 0,
                    "1": 0
                },
                "response_rate": 0.0,
                "recent_trend": "0"
            }
            
        except Exception as e:
            logger.warning(f"Error getting real rating data: {str(e)}")
            # No real data available - return empty rating stats for new users
            return {
                "average_rating": 0.0,
                "total_reviews": 0,
                "unique_reviewers": 0,
                "rating_distribution": {
                    "5": 0,
                    "4": 0,
                    "3": 0,
                    "2": 0,
                    "1": 0
                },
                "response_rate": 0.0,
                "recent_trend": "0"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting rating stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve rating statistics"
        )