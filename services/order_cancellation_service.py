"""
Order Cancellation Service
Implements industry-standard order cancellation patterns based on Amazon/Shopify architecture
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models.order import Order, OrderStatus, PaymentStatus, OrderItem
from models.order_cancellation import OrderCancellation, CancellationReason, RefundStatus
from models.product import Product
from schemas.order_cancellation import CancellationRequest, CancellationResponse, CancellationPolicy
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)

class OrderCancellationService:
    """
    Order cancellation service implementing industry best practices:
    - Saga pattern for distributed transactions
    - State machine for order status management
    - Compensating transactions for rollback
    - Event-driven notifications
    """

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    def check_cancellation_policy(self, order_id: str, user_id: str) -> CancellationPolicy:
        """
        Check if order can be cancelled based on business rules
        Following Amazon/Shopify patterns for cancellation windows
        """
        try:
            # Query order without the cancellation fields that may not exist yet
            order = self.db.query(Order).filter(
                and_(Order.id == order_id, Order.customer_id == user_id)
            ).first()

            if not order:
                return CancellationPolicy(
                    can_cancel=False,
                    reason="Order not found or access denied"
                )

            # Check if already cancelled
            if order.status == OrderStatus.CANCELLED:
                return CancellationPolicy(
                    can_cancel=False,
                    reason="Order is already cancelled"
                )

            # Check if order is delivered
            if order.status in [OrderStatus.DELIVERED, OrderStatus.RETURNED]:
                return CancellationPolicy(
                    can_cancel=False,
                    reason="Cannot cancel delivered orders. Please use return process."
                )

            # Check time-based cancellation window (following industry standards)
            time_since_order = datetime.utcnow() - order.created_at

            # Different time windows based on order status
            if order.status == OrderStatus.PENDING:
                # 24 hours for pending orders (customer-friendly window)
                if time_since_order > timedelta(hours=24):
                    return CancellationPolicy(
                        can_cancel=False,
                        reason="Cancellation window expired (24 hours for pending orders)",
                        time_limit_hours=24
                    )
            elif order.status == OrderStatus.PROCESSING:
                # 12 hours for processing orders (customer-friendly window)
                if time_since_order > timedelta(hours=12):
                    return CancellationPolicy(
                        can_cancel=False,
                        reason="Cancellation window expired (12 hours for processing orders)",
                        time_limit_hours=12
                    )
            elif order.status in [OrderStatus.PICKED_UP, OrderStatus.IN_TRANSIT, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED]:
                # No cancellation for shipped/delivered orders
                return CancellationPolicy(
                    can_cancel=False,
                    reason="Cannot cancel shipped or delivered orders. Please contact support for returns."
                )

            # Calculate refund percentage based on timing
            refund_percentage = 100.0
            cancellation_fee = 0.0

            # Apply fees for late cancellations (industry practice)
            if order.status == OrderStatus.PROCESSING and time_since_order > timedelta(minutes=30):
                refund_percentage = 95.0
                cancellation_fee = float(order.total_amount) * 0.05

            return CancellationPolicy(
                can_cancel=True,
                reason="Order can be cancelled",
                refund_percentage=refund_percentage,
                cancellation_fee=cancellation_fee
            )

        except Exception as e:
            logger.error(f"Error checking cancellation policy for order {order_id}: {str(e)}")
            return CancellationPolicy(
                can_cancel=False,
                reason="System error. Please try again later."
            )

    async def cancel_order(self, order_id: str, user_id: str, cancellation_request: CancellationRequest) -> CancellationResponse:
        """
        Cancel order using Saga pattern for distributed transaction management
        Implements compensating transactions for rollback capability
        """
        try:
            # Step 1: Validate cancellation policy
            policy = self.check_cancellation_policy(order_id, user_id)
            if not policy.can_cancel:
                return CancellationResponse(
                    success=False,
                    message=policy.reason,
                    order_id=order_id,
                    cancelled_at=datetime.utcnow()
                )

            # Step 2: Get order details
            order = self.db.query(Order).filter(
                and_(Order.id == order_id, Order.customer_id == user_id)
            ).first()

            if not order:
                return CancellationResponse(
                    success=False,
                    message="Order not found",
                    order_id=order_id,
                    cancelled_at=datetime.utcnow()
                )

            # Step 3: Begin Saga Transaction - Create cancellation record
            cancellation = OrderCancellation(
                order_id=order_id,
                cancelled_by=user_id,
                reason=CancellationReason(cancellation_request.reason),
                description=cancellation_request.description,
                refund_requested=cancellation_request.refund_requested,
                refund_amount=float(order.total_amount) * (policy.refund_percentage / 100),
                refund_status=RefundStatus.PENDING if cancellation_request.refund_requested else RefundStatus.CANCELLED
            )

            self.db.add(cancellation)

            # Step 4: Update order status (State Machine Pattern)
            old_status = order.status
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.utcnow()
            order.cancellation_reason = cancellation_request.reason.value
            order.status_updated_at = datetime.utcnow()

            # Step 5: Inventory Reconciliation (compensating transaction)
            items_restocked = False
            if cancellation_request.restock_items:
                items_restocked = await self._restock_order_items(order_id)
                cancellation.items_restocked = items_restocked
                if items_restocked:
                    cancellation.restock_completed_at = datetime.utcnow()

            # Step 6: Process refund if requested
            refund_reference = None
            if cancellation_request.refund_requested and order.payment_status == PaymentStatus.PAID:
                # In production, integrate with payment gateway (Tranzak, Stripe, etc.)
                refund_reference = await self._process_refund(order, cancellation.refund_amount)
                cancellation.refund_reference = refund_reference

            # Step 7: Commit transaction
            cancellation.processed_at = datetime.utcnow()
            self.db.commit()

            # Step 8: Send notifications (Event-driven pattern)
            await self._send_cancellation_notifications(order, cancellation)

            logger.info(f"Order {order_id} cancelled successfully by user {user_id}")

            return CancellationResponse(
                success=True,
                message="Order cancelled successfully",
                order_id=order_id,
                cancellation_id=cancellation.id,
                refund_amount=cancellation.refund_amount,
                refund_status=cancellation.refund_status.value,
                estimated_refund_time="3-5 business days" if refund_reference else None,
                cancelled_at=cancellation.cancelled_at,
                items_restocked=items_restocked
            )

        except Exception as e:
            # Compensating transaction - rollback on failure
            self.db.rollback()
            logger.error(f"Error cancelling order {order_id}: {str(e)}")

            return CancellationResponse(
                success=False,
                message="Failed to cancel order. Please try again.",
                order_id=order_id,
                cancelled_at=datetime.utcnow()
            )

    async def _restock_order_items(self, order_id: str) -> bool:
        """
        Restock inventory items (compensating transaction for inventory deduction)
        Following Amazon's inventory reconciliation pattern
        """
        try:
            order_items = self.db.query(OrderItem).filter(OrderItem.order_id == order_id).all()

            for item in order_items:
                product = self.db.query(Product).filter(Product.id == item.product_id).first()
                if product:
                    # Restore inventory
                    product.stock_quantity += item.quantity
                    logger.info(f"Restocked {item.quantity} units of product {product.id}")

            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Error restocking items for order {order_id}: {str(e)}")
            self.db.rollback()
            return False

    async def _process_refund(self, order: Order, refund_amount: float) -> Optional[str]:
        """
        Process refund through payment gateway
        In production, integrate with Tranzak, Stripe, etc.
        """
        try:
            # Simulate payment gateway refund
            # In production, call actual payment gateway API
            refund_reference = f"REF_{order.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Update payment status
            order.payment_status = PaymentStatus.REFUNDED

            logger.info(f"Refund processed for order {order.id}: {refund_amount} XAF, Reference: {refund_reference}")
            return refund_reference

        except Exception as e:
            logger.error(f"Error processing refund for order {order.id}: {str(e)}")
            return None

    async def _send_cancellation_notifications(self, order: Order, cancellation: OrderCancellation):
        """
        Send notifications using event-driven pattern
        Following industry standards for customer communication
        """
        try:
            # Customer notification
            await self.notification_service.create_notification(
                user_id=order.customer_id,
                title="Order Cancelled",
                message=f"Your order #{order.id} has been cancelled successfully.",
                notification_type="order_cancellation",
                related_id=order.id
            )

            # Vendor notification (if applicable)
            if order.shop_id:
                shop_owner = self.db.query(Order).join(Shop).filter(Shop.id == order.shop_id).first()
                if shop_owner:
                    await self.notification_service.create_notification(
                        user_id=shop_owner.owner_id,
                        title="Order Cancelled",
                        message=f"Order #{order.id} has been cancelled by customer.",
                        notification_type="order_cancellation",
                        related_id=order.id
                    )

        except Exception as e:
            logger.error(f"Error sending cancellation notifications: {str(e)}")

    def get_cancellation_history(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's order cancellation history"""
        try:
            cancellations = self.db.query(OrderCancellation).join(Order).filter(
                Order.customer_id == user_id
            ).order_by(OrderCancellation.cancelled_at.desc()).limit(limit).all()

            return [
                {
                    "cancellation_id": c.id,
                    "order_id": c.order_id,
                    "reason": c.reason.value,
                    "cancelled_at": c.cancelled_at.isoformat(),
                    "refund_amount": float(c.refund_amount) if c.refund_amount else None,
                    "refund_status": c.refund_status.value,
                    "items_restocked": c.items_restocked
                }
                for c in cancellations
            ]

        except Exception as e:
            logger.error(f"Error getting cancellation history for user {user_id}: {str(e)}")
            return []