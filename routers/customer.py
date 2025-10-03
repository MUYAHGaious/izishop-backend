from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from database.connection import get_db
from routers.auth import get_current_user
from models.user import User
from models.order import Order, OrderStatus, OrderItem
from models.product import Product
from models.shop import Shop
from models.payment import Payment
from models.order_cancellation import OrderCancellation
from core.response import success_response, error_response
from schemas.order_cancellation import CancellationRequest, CancellationResponse, CancellationPolicy
from services.order_cancellation_service import OrderCancellationService
from services.order_status_service import OrderStatusService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/stats")
async def get_customer_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customer statistics"""
    try:
        logger.info(f"📊 Getting customer stats for user: {current_user.id} ({current_user.email})")

        # Debug: Check all orders in database
        all_orders = db.query(Order).all()
        logger.info(f"  🔍 Total orders in entire database: {len(all_orders)}")

        # Debug: Check orders for this customer
        customer_orders = db.query(Order).filter(Order.customer_id == current_user.id).all()
        logger.info(f"  🔍 Orders for customer {current_user.id}: {len(customer_orders)}")
        if customer_orders:
            for order in customer_orders:
                logger.info(f"    Order ID: {order.id}, Status: {order.status}, Amount: {order.total_amount}, Customer ID: {order.customer_id}")

        # Get customer's order statistics
        total_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == current_user.id
        ).scalar() or 0

        logger.info(f"  📦 Total orders found: {total_orders}")

        # Get total spent (sum of ALL orders regardless of status)
        total_spent = db.query(func.sum(Order.total_amount)).filter(
            Order.customer_id == current_user.id
        ).scalar() or 0

        logger.info(f"  💰 Total spent: {total_spent}")

        # Get recent orders count (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == current_user.id,
            Order.created_at >= thirty_days_ago
        ).scalar() or 0

        logger.info(f"  📅 Recent orders (30 days): {recent_orders}")

        # Get pending orders (active orders)
        pending_orders = db.query(func.count(Order.id)).filter(
            Order.customer_id == current_user.id,
            Order.status.in_([OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.IN_TRANSIT])
        ).scalar() or 0

        logger.info(f"  ⏳ Active orders: {pending_orders}")

        stats = {
            "total_orders": total_orders,
            "total_spent": float(total_spent),
            "recent_orders": recent_orders,
            "pending_orders": pending_orders,
            "avg_order_value": float(total_spent / total_orders) if total_orders > 0 else 0
        }

        logger.info(f"✅ Returning stats: {stats}")

        # Return stats directly for frontend compatibility
        return stats

    except Exception as e:
        logger.error(f"❌ Error getting customer stats: {str(e)}")
        logger.exception(e)
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
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customer orders with pagination"""
    try:
        logger.info(f"====== GET CUSTOMER ORDERS CALLED ======")
        logger.info(f"Customer ID: {current_user.id}")
        logger.info(f"Customer Email: {current_user.email}")
        logger.info(f"Page: {page}, Limit: {limit}, Status: {status}")

        # Build query
        query = db.query(Order).filter(Order.customer_id == current_user.id)

        logger.info(f"Query built for customer_id: {current_user.id}")

        if status:
            try:
                order_status = OrderStatus(status)
                query = query.filter(Order.status == order_status)
            except ValueError:
                # If invalid status, return empty result
                return {
                    "orders": [],
                    "total": 0,
                    "page": page,
                    "totalPages": 0
                }

        # Get total count for pagination
        total_orders = query.count()
        total_pages = max(1, (total_orders + limit - 1) // limit)

        # Apply pagination
        offset = (page - 1) * limit
        orders = query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()

        logger.info(f"Found {len(orders)} orders for customer {current_user.id}")

        order_list = []
        for order in orders:
            logger.info(f"Processing order {order.id}")

            # Get shop info if available
            shop = db.query(Shop).filter(Shop.id == order.shop_id).first() if hasattr(order, 'shop_id') and order.shop_id else None

            # Get payment information
            payment_method = "N/A"
            try:
                payment = db.query(Payment).filter(Payment.order_id == order.id).first()
                if payment and payment.payment_method:
                    # Map payment method to user-friendly names
                    payment_method_mapping = {
                        'MTN_MOMO': 'MTN Mobile Money',
                        'ORANGE_MONEY': 'Orange Money',
                        'VISA': 'Visa Card',
                        'mtn_money': 'MTN Mobile Money',
                        'orange_money': 'Orange Money',
                        'visa': 'Visa Card',
                        'card': 'Credit/Debit Card'
                    }
                    payment_method = payment_method_mapping.get(payment.payment_method, payment.payment_method)
            except Exception as e:
                logger.warning(f"Failed to fetch payment info for order {order.id}: {str(e)}")

            # Get order items (query separately since relationship is commented out)
            order_items = []
            try:
                logger.info(f"Querying OrderItem for order_id: {order.id}")
                items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
                logger.info(f"Found {len(items)} items for order {order.id}")
                for item in items:
                    product = db.query(Product).filter(Product.id == item.product_id).first()
                    # Get first image from image_urls array (it's a JSON field)
                    product_image = None
                    if product and product.image_urls:
                        if isinstance(product.image_urls, list) and len(product.image_urls) > 0:
                            product_image = product.image_urls[0]
                        elif isinstance(product.image_urls, str):
                            # Sometimes it might be stored as a string
                            import json
                            try:
                                urls = json.loads(product.image_urls)
                                if isinstance(urls, list) and len(urls) > 0:
                                    product_image = urls[0]
                            except:
                                pass

                    order_items.append({
                        "id": item.id,
                        "product_id": item.product_id,
                        "product_name": product.name if product else "Unknown Product",
                        "product_image": product_image,
                        "quantity": item.quantity,
                        "unit_price": float(item.unit_price),
                        "total_price": float(item.total_price) if hasattr(item, 'total_price') else float(item.unit_price * item.quantity),
                        "shop_id": order.shop_id if order.shop_id else "",
                        "shop_name": shop.name if shop else "Unknown Shop"
                    })
            except Exception as e:
                logger.warning(f"Failed to fetch order items for order {order.id}: {str(e)}")
                # Continue without items if there's an error

            order_data = {
                "id": order.id,
                "order_number": order.id,  # Use order ID as order number for now
                "total_amount": float(order.total_amount),
                "status": order.status.value if order.status else "unknown",
                "payment_status": order.payment_status.value if order.payment_status else "unknown",
                "payment_method": payment_method,
                "shipping_address": order.shipping_address,
                "tracking_number": order.tracking_number,
                "notes": order.notes,
                "created_at": order.created_at.isoformat() if order.created_at else None,
                "updated_at": order.updated_at.isoformat() if order.updated_at else None,
                "shop_name": shop.name if shop else "Unknown Shop",
                "items": order_items
            }
            logger.info(f"Order {order.id}: returning {len(order_items)} items")
            if order_items:
                logger.info(f"First item: {order_items[0]}")
            order_list.append(order_data)

        # Return response in expected format
        return {
            "orders": order_list,
            "total": total_orders,
            "page": page,
            "totalPages": total_pages
        }

    except Exception as e:
        logger.error(f"Error getting customer orders: {str(e)}")
        # Return empty result on error
        return {
            "orders": [],
            "total": 0,
            "page": page,
            "totalPages": 0
        }

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

@router.get("/orders/{order_id}/cancellation-policy")
async def get_order_cancellation_policy(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if order can be cancelled and get cancellation policy
    Following industry standards for cancellation windows and policies
    """
    try:
        cancellation_service = OrderCancellationService(db)
        policy = cancellation_service.check_cancellation_policy(order_id, current_user.id)
        return {
            "can_cancel": policy.can_cancel,
            "reason": policy.reason,
            "cancellation_deadline": policy.cancellation_deadline,
            "refund_amount": policy.refund_amount,
            "processing_fee": policy.processing_fee
        }
    except Exception as e:
        logger.error(f"Error checking cancellation policy for order {order_id}: {str(e)}")
        return {
            "can_cancel": False,
            "reason": "System error. Please try again later."
        }

@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    cancellation_request: CancellationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> CancellationResponse:
    """
    Cancel an order using industry-standard cancellation process
    Implements Saga pattern for distributed transaction management
    """
    try:
        cancellation_service = OrderCancellationService(db)
        result = await cancellation_service.cancel_order(
            order_id=order_id,
            user_id=current_user.id,
            cancellation_request=cancellation_request
        )

        if result.success:
            logger.info(f"Order {order_id} cancelled successfully by user {current_user.id}")
        else:
            logger.warning(f"Order cancellation failed for {order_id}: {result.message}")

        return result

    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return CancellationResponse(
            success=False,
            message="Failed to cancel order. Please try again later.",
            order_id=order_id,
            cancelled_at=datetime.utcnow()
        )

@router.get("/orders/cancellation-history")
async def get_cancellation_history(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get customer's order cancellation history"""
    try:
        cancellation_service = OrderCancellationService(db)
        history = cancellation_service.get_cancellation_history(
            user_id=current_user.id,
            limit=limit
        )
        return {
            "cancellation_history": history,
            "total": len(history)
        }
    except Exception as e:
        logger.error(f"Error getting cancellation history for user {current_user.id}: {str(e)}")
        return {
            "cancellation_history": [],
            "total": 0
        }

@router.get("/orders/{order_id}/timeline")
async def get_order_timeline(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get enhanced timeline for a specific order"""
    try:
        # Verify order belongs to user
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.customer_id == current_user.id
        ).first()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Get enhanced timeline using the order status service
        status_service = OrderStatusService(db)
        timeline = status_service.get_order_timeline(order)

        # Get next expected status and estimated delivery
        next_status = status_service.get_next_expected_status(order.status)
        estimated_delivery = status_service.get_estimated_delivery_update(order)

        return {
            "order_id": order_id,
            "current_status": order.status.value,
            "timeline": timeline,
            "next_expected_status": next_status.value if next_status else None,
            "estimated_delivery": estimated_delivery.isoformat() if estimated_delivery else None,
            "progress_percentage": _get_progress_percentage(order.status)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting timeline for order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving order timeline")

@router.get("/orders/{order_id}/status-history")
async def get_order_status_history(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed status history for a specific order"""
    try:
        # Verify order belongs to user
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.customer_id == current_user.id
        ).first()

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Get status history
        history = db.query(OrderStatusHistory).filter(
            OrderStatusHistory.order_id == order_id
        ).order_by(desc(OrderStatusHistory.changed_at)).all()

        status_history = []
        for record in history:
            status_history.append({
                "id": record.id,
                "old_status": record.old_status,
                "new_status": record.new_status,
                "changed_at": record.changed_at.isoformat() if record.changed_at else None,
                "notes": record.notes,
                "metadata": record.metadata_json
            })

        return {
            "order_id": order_id,
            "status_history": status_history
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status history for order {order_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error retrieving order status history")

def _get_progress_percentage(status: OrderStatus) -> int:
    """Helper function to calculate progress percentage"""
    progress_map = {
        OrderStatus.PENDING: 5,
        OrderStatus.CONFIRMED: 15,
        OrderStatus.PAYMENT_PROCESSING: 20,
        OrderStatus.PAYMENT_CONFIRMED: 25,
        OrderStatus.PROCESSING: 35,
        OrderStatus.PICKING: 45,
        OrderStatus.PACKED: 55,
        OrderStatus.READY_FOR_PICKUP: 65,
        OrderStatus.PICKED_UP: 75,
        OrderStatus.IN_TRANSIT: 85,
        OrderStatus.OUT_FOR_DELIVERY: 95,
        OrderStatus.DELIVERED: 100,
        OrderStatus.COMPLETED: 100
    }
    return progress_map.get(status, 0)