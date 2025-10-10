"""
Analytics and statistics endpoints for IziShopin
"""
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.product import Product
from models.order import Order, OrderItem
from models.shop import Shop
from typing import Dict, Any

router = APIRouter(prefix="/api/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

@router.get("/user-stats")
async def get_user_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive user statistics including products, orders, and revenue"""
    try:
        logger.info(f"📊 Getting user stats for user: {current_user.id}")
        user_id = current_user.id
        
        # Get current month start and end
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = month_start + timedelta(days=32)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        
        # Get user's shop if they have one
        user_shop = db.query(Shop).filter(Shop.owner_id == user_id).first()
        shop_id = user_shop.id if user_shop else None
        
        # Count products listed by user
        total_products = db.query(Product).filter(
            Product.seller_id == user_id,
            Product.is_active == True
        ).count()
        
        # Count products listed this month
        products_this_month = db.query(Product).filter(
            Product.seller_id == user_id,
            Product.is_active == True,
            Product.created_at >= month_start,
            Product.created_at <= month_end
        ).count()
        
        # Count orders received (if user has a shop)
        total_orders = 0
        orders_this_month = 0
        total_revenue = 0.0
        revenue_this_month = 0.0
        
        if shop_id:
            # Total orders for the shop
            total_orders = db.query(Order).filter(Order.shop_id == shop_id).count()
            
            # Orders this month
            orders_this_month = db.query(Order).filter(
                Order.shop_id == shop_id,
                Order.created_at >= month_start,
                Order.created_at <= month_end
            ).count()
            
            # Calculate total revenue from completed orders (using uppercase enum values)
            completed_orders = db.query(Order).filter(
                Order.shop_id == shop_id,
                Order.status.in_(['DELIVERED', 'IN_TRANSIT', 'PROCESSING', 'COMPLETED', 'OUT_FOR_DELIVERY'])
            ).all()

            total_revenue = sum(float(order.total_amount) for order in completed_orders)

            # Revenue this month
            completed_orders_this_month = db.query(Order).filter(
                Order.shop_id == shop_id,
                Order.status.in_(['DELIVERED', 'IN_TRANSIT', 'PROCESSING', 'COMPLETED', 'OUT_FOR_DELIVERY']),
                Order.created_at >= month_start,
                Order.created_at <= month_end
            ).all()

            revenue_this_month = sum(float(order.total_amount) for order in completed_orders_this_month)

        # Get pending orders count (orders that need attention)
        pending_orders = 0
        if shop_id:
            pending_orders = db.query(Order).filter(
                Order.shop_id == shop_id,
                Order.status.in_(['PENDING', 'CONFIRMED', 'PROCESSING', 'IN_TRANSIT'])
            ).count()

        # Get low stock items count (stock <= 10)
        low_stock_items = 0
        if shop_id:
            low_stock_items = db.query(Product).filter(
                Product.shop_id == shop_id,
                Product.is_active == True,
                Product.stock <= 10
            ).count()

        logger.info(f"✅ User stats calculated: products={total_products}, orders={total_orders}, revenue={total_revenue}, pending={pending_orders}, low_stock={low_stock_items}")

        # Calculate usage limits based on user role
        if current_user.role == 'SHOP_OWNER':
            product_limit = None  # Unlimited
            storage_limit = None  # Unlimited
        elif current_user.role == 'CASUAL_SELLER':
            product_limit = 10
            storage_limit = 100  # MB
        else:
            product_limit = 0
            storage_limit = 10  # MB
        
        # Calculate usage percentages
        product_usage_percent = 0
        if product_limit:
            product_usage_percent = min((total_products / product_limit) * 100, 100)
        
        # Mock storage usage (in a real app, you'd calculate actual file sizes)
        storage_used = total_products * 2  # Assume 2MB per product
        storage_usage_percent = 0
        if storage_limit:
            storage_usage_percent = min((storage_used / storage_limit) * 100, 100)
        
        return {
            "success": True,
            "data": {
                "overview": {
                    "total_products": total_products,
                    "total_orders": total_orders,
                    "total_revenue": round(total_revenue, 2),
                    "products_this_month": products_this_month,
                    "orders_this_month": orders_this_month,
                    "revenue_this_month": round(revenue_this_month, 2),
                    "pending_orders": pending_orders,
                    "low_stock_items": low_stock_items
                },
                "usage": {
                    "products": {
                        "used": total_products,
                        "limit": product_limit,
                        "percentage": round(product_usage_percent, 1)
                    },
                    "storage": {
                        "used_mb": storage_used,
                        "limit_mb": storage_limit,
                        "percentage": round(storage_usage_percent, 1)
                    }
                },
                "subscription": {
                    "plan": current_user.role,
                    "has_shop": shop_id is not None,
                    "shop_id": shop_id
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting user statistics: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user statistics"
        )

@router.get("/recent-activity")
async def get_recent_activity(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Get recent activity for the user"""
    try:
        user_id = current_user.id
        activities = []
        
        # Get user's shop
        user_shop = db.query(Shop).filter(Shop.owner_id == user_id).first()
        
        # Recent products created
        recent_products = db.query(Product).filter(
            Product.seller_id == user_id
        ).order_by(desc(Product.created_at)).limit(5).all()
        
        for product in recent_products:
            activities.append({
                "type": "product_created",
                "title": f"Created product: {product.name}",
                "description": f"Listed for ${product.price}",
                "timestamp": product.created_at.isoformat(),
                "icon": "package"
            })
        
        # Recent orders (if user has a shop)
        if user_shop:
            recent_orders = db.query(Order).filter(
                Order.shop_id == user_shop.id
            ).order_by(desc(Order.created_at)).limit(5).all()
            
            for order in recent_orders:
                activities.append({
                    "type": "order_received",
                    "title": f"New order received",
                    "description": f"Order #{order.id[:8]} - ${order.total_amount}",
                    "timestamp": order.created_at.isoformat(),
                    "icon": "shopping-cart"
                })
        
        # Sort activities by timestamp and limit
        activities.sort(key=lambda x: x['timestamp'], reverse=True)
        activities = activities[:limit]
        
        return {
            "success": True,
            "data": activities
        }
        
    except Exception as e:
        logger.error(f"Error getting recent activity: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve recent activity"
        )