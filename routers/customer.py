from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from database.connection import get_db
from routers.auth import get_current_user
from models.user import User
from models.order import Order, OrderStatus
from models.product import Product
from core.response import success_response, error_response

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/stats")
async def get_customer_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customer statistics"""
    try:
        # Get customer's order statistics
        total_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == current_user.id
        ).scalar() or 0
        
        # Get total spent
        total_spent = db.query(func.sum(Order.total_amount)).filter(
            Order.customer_id == current_user.id,
            Order.status.in_([OrderStatus.DELIVERED, OrderStatus.SHIPPED])
        ).scalar() or 0
        
        # Get recent orders count (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == current_user.id,
            Order.created_at >= thirty_days_ago
        ).scalar() or 0
        
        # Get pending orders
        pending_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == current_user.id,
            Order.status == OrderStatus.PENDING
        ).scalar() or 0
        
        stats = {
            "total_orders": total_orders,
            "total_spent": float(total_spent),
            "recent_orders": recent_orders,
            "pending_orders": pending_orders,
            "avg_order_value": float(total_spent / total_orders) if total_orders > 0 else 0
        }
        
        # Return stats directly for frontend compatibility
        return stats
        
    except Exception as e:
        logger.error(f"Error getting customer stats: {str(e)}")
        # Return default stats on error to prevent frontend crashes
        return {
            "total_orders": 0,
            "total_spent": 0.0,
            "recent_orders": 0,
            "pending_orders": 0,
            "avg_order_value": 0.0
        }

@router.get("/orders")
async def get_customer_orders(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customer orders"""
    try:
        query = db.query(Order).filter(Order.customer_id == current_user.id)
        
        if status:
            query = query.filter(Order.status == status)
        
        orders = query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
        
        order_list = []
        for order in orders:
            order_data = {
                "id": order.id,
                "total_amount": float(order.total_amount),
                "status": order.status.value if order.status else None,
                "payment_status": order.payment_status.value if order.payment_status else None,
                "shipping_address": order.shipping_address,
                "tracking_number": order.tracking_number,
                "notes": order.notes,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None
            }
            order_list.append(order_data)
        
        # Return the order list directly as an array for frontend compatibility
        return order_list
        
    except Exception as e:
        logger.error(f"Error getting customer orders: {str(e)}")
        # Return empty array on error to prevent frontend crashes
        return []

@router.get("/recent-orders")
async def get_recent_orders(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get recent orders for customer dashboard"""
    try:
        orders = db.query(Order).filter(
            Order.customer_id == current_user.id
        ).order_by(desc(Order.created_at)).limit(limit).all()
        
        order_list = []
        for order in orders:
            order_data = {
                "id": order.id,
                "total_amount": float(order.total_amount),
                "status": order.status.value if order.status else "PENDING",
                "payment_status": order.payment_status.value if order.payment_status else "PENDING",
                "shipping_address": order.shipping_address,
                "tracking_number": order.tracking_number,
                "notes": order.notes,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None
            }
            order_list.append(order_data)
        
        # Return just the array for easier frontend consumption
        return order_list
        
    except Exception as e:
        logger.error(f"Error getting recent orders: {str(e)}")
        # Return empty array on error to prevent frontend crashes
        return []

@router.get("/wishlist")
async def get_customer_wishlist(
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customer wishlist (placeholder)"""
    try:
        # For now, return empty wishlist since wishlist functionality is not implemented
        # Return empty array directly for frontend compatibility
        return []
        
    except Exception as e:
        logger.error(f"Error getting customer wishlist: {str(e)}")
        # Return empty array on error to prevent frontend crashes
        return []