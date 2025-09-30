"""
Order Status Notification Handler
Handles order status change events and creates appropriate notifications
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

from core.event_system import SystemEvent, EventType, event_handler
from services.notification_service import NotificationService
from models.notification import NotificationType, NotificationPriority
from models.user import User
from models.order import Order
from database.connection import get_db

logger = logging.getLogger(__name__)

class OrderNotificationHandler:
    """Handles order-related events and creates notifications"""

    def __init__(self):
        self.notification_service = None

    def get_notification_service(self):
        """Get notification service instance"""
        if not self.notification_service:
            # Get a database session
            db_gen = get_db()
            db = next(db_gen)
            self.notification_service = NotificationService(db)
        return self.notification_service

    async def handle_order_status_change(self, event: SystemEvent):
        """Handle order status change events"""
        try:
            data = event.data
            order_id = data.get('order_id')
            customer_id = data.get('customer_id')
            old_status = data.get('old_status')
            new_status = data.get('new_status')
            estimated_delivery = data.get('estimated_delivery')

            logger.info(f"Processing order status change notification: {order_id} {old_status} -> {new_status}")

            # Get notification service
            notification_service = self.get_notification_service()

            # Determine notification priority based on status
            priority = self._get_notification_priority(new_status)

            # Create customer-friendly message
            title, message = self._get_status_message(new_status, estimated_delivery)

            # Create notification
            await notification_service.create_notification(
                user_id=customer_id,
                title=title,
                message=message,
                notification_type=NotificationType.ORDER,
                priority=priority,
                related_id=order_id
            )

            logger.info(f"Created notification for order {order_id} status change to {new_status}")

        except Exception as e:
            logger.error(f"Error handling order status change event: {str(e)}")

    def _get_notification_priority(self, status: str) -> NotificationPriority:
        """Determine notification priority based on order status"""
        high_priority_statuses = [
            'delivered', 'cancelled', 'exception', 'delivery_attempted', 'returned'
        ]
        medium_priority_statuses = [
            'confirmed', 'payment_confirmed', 'out_for_delivery', 'shipped', 'in_transit'
        ]

        if status in high_priority_statuses:
            return NotificationPriority.HIGH
        elif status in medium_priority_statuses:
            return NotificationPriority.MEDIUM
        else:
            return NotificationPriority.LOW

    def _get_status_message(self, status: str, estimated_delivery: str = None) -> tuple[str, str]:
        """Generate customer-friendly notification messages"""

        status_messages = {
            'pending': (
                "Order Received!",
                "We've received your order and are reviewing it. You'll hear from us soon!"
            ),
            'confirmed': (
                "Order Confirmed!",
                "Great news! Your order has been confirmed and we're preparing it for you."
            ),
            'payment_processing': (
                "Processing Payment",
                "We're securely processing your payment. This usually takes just a few moments."
            ),
            'payment_confirmed': (
                "Payment Confirmed!",
                "Your payment has been processed successfully. We're now preparing your order."
            ),
            'processing': (
                "Order Being Prepared",
                "Your order is being carefully prepared by our team. We'll update you when it's ready!"
            ),
            'picking': (
                "Picking Your Items",
                "Our team is carefully selecting your items to ensure quality."
            ),
            'packed': (
                "Order Packed!",
                "Your order has been packed and is ready for pickup by our delivery partner."
            ),
            'ready_for_pickup': (
                "Ready for Pickup",
                "Your order is ready for pickup by our delivery partner."
            ),
            'picked_up': (
                "Order Picked Up",
                "Your order has been picked up by our delivery partner and is on its way!"
            ),
            'in_transit': (
                "Order on the Way!",
                f"Your order is in transit{' and should arrive by ' + estimated_delivery if estimated_delivery else ''}."
            ),
            'out_for_delivery': (
                "Out for Delivery!",
                f"Your order is out for delivery{' and should arrive today' if estimated_delivery else ''}. Keep an eye out!"
            ),
            'delivery_attempted': (
                "Delivery Attempted",
                "Our delivery partner attempted to deliver your order but couldn't complete it. They'll try again soon."
            ),
            'delivered': (
                "Order Delivered!",
                "Great! Your order has been successfully delivered. Thank you for shopping with us!"
            ),
            'completed': (
                "Order Complete",
                "Your order has been completed. We hope you love your purchase!"
            ),
            'cancelled': (
                "Order Cancelled",
                "Your order has been cancelled. If you didn't request this, please contact support."
            ),
            'returned': (
                "Order Returned",
                "Your order has been returned and we're processing your refund."
            ),
            'refunded': (
                "Refund Processed",
                "Your refund has been processed and should appear in your account within 3-5 business days."
            ),
            'exception': (
                "Delivery Update",
                "There's been a small delay with your order. Our team is working to resolve it quickly."
            )
        }

        return status_messages.get(status, (
            "Order Update",
            "Your order status has been updated. Check your order details for more information."
        ))

# Initialize the handler
order_notification_handler = OrderNotificationHandler()

# Register the event handler
from core.event_system import event_bus, EventType

# Register the handler function (not the method)
@event_handler(EventType.ORDER_STATUS_CHANGED)
async def handle_order_status_change_event(event: SystemEvent):
    """Global handler function for order status change events"""
    await order_notification_handler.handle_order_status_change(event)