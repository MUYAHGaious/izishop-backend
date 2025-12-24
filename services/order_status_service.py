"""
Enhanced Order Status Service for IziShop
Implements tech-giant level order status management with automatic transitions and notifications
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import logging

from models.order import Order, OrderStatus, OrderStatusHistory
from models.user import User
from services.notification_service import NotificationService
from models.notification import NotificationType, NotificationPriority
from core.event_system import event_bus, OrderStatusChangeEvent, EventType

logger = logging.getLogger(__name__)

class OrderStatusService:
    """Service for managing enhanced order status transitions and notifications"""

    # Define the allowed status transitions
    STATUS_TRANSITIONS = {
        OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
        OrderStatus.CONFIRMED: [OrderStatus.PAYMENT_PROCESSING, OrderStatus.CANCELLED],
        OrderStatus.PAYMENT_PROCESSING: [OrderStatus.PAYMENT_CONFIRMED, OrderStatus.CANCELLED],
        OrderStatus.PAYMENT_CONFIRMED: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
        OrderStatus.PROCESSING: [OrderStatus.PICKING, OrderStatus.CANCELLED],
        OrderStatus.PICKING: [OrderStatus.PACKED, OrderStatus.CANCELLED],
        OrderStatus.PACKED: [OrderStatus.READY_FOR_PICKUP, OrderStatus.CANCELLED],
        OrderStatus.READY_FOR_PICKUP: [OrderStatus.PICKED_UP, OrderStatus.CANCELLED],
        OrderStatus.PICKED_UP: [OrderStatus.IN_TRANSIT, OrderStatus.EXCEPTION],
        OrderStatus.IN_TRANSIT: [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.EXCEPTION],
        OrderStatus.OUT_FOR_DELIVERY: [OrderStatus.DELIVERED, OrderStatus.DELIVERY_ATTEMPTED, OrderStatus.EXCEPTION],
        OrderStatus.DELIVERY_ATTEMPTED: [OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED, OrderStatus.RETURNED],
        OrderStatus.DELIVERED: [OrderStatus.COMPLETED, OrderStatus.RETURNED],
        OrderStatus.COMPLETED: [],  # Final state
        OrderStatus.CANCELLED: [OrderStatus.REFUNDED],  # Can be refunded after cancellation
        OrderStatus.RETURNED: [OrderStatus.REFUNDED],
        OrderStatus.REFUNDED: [],  # Final state
        OrderStatus.EXCEPTION: [OrderStatus.IN_TRANSIT, OrderStatus.RETURNED, OrderStatus.CANCELLED]
    }

    # Status display names for customer communication
    STATUS_DISPLAY_NAMES = {
        OrderStatus.PENDING: "Order Placed",
        OrderStatus.CONFIRMED: "Order Confirmed",
        OrderStatus.PAYMENT_PROCESSING: "Processing Payment",
        OrderStatus.PAYMENT_CONFIRMED: "Payment Confirmed",
        OrderStatus.PROCESSING: "Preparing Your Order",
        OrderStatus.PICKING: "Picking Items",
        OrderStatus.PACKED: "Order Packed",
        OrderStatus.READY_FOR_PICKUP: "Ready for Pickup",
        OrderStatus.PICKED_UP: "Picked Up by Carrier",
        OrderStatus.IN_TRANSIT: "In Transit",
        OrderStatus.OUT_FOR_DELIVERY: "Out for Delivery",
        OrderStatus.DELIVERY_ATTEMPTED: "Delivery Attempted",
        OrderStatus.DELIVERED: "Delivered",
        OrderStatus.COMPLETED: "Order Completed",
        OrderStatus.CANCELLED: "Cancelled",
        OrderStatus.RETURNED: "Returned",
        OrderStatus.REFUNDED: "Refunded",
        OrderStatus.EXCEPTION: "Delivery Exception"
    }

    # Customer-friendly descriptions
    STATUS_DESCRIPTIONS = {
        OrderStatus.PENDING: "We've received your order and are processing it.",
        OrderStatus.CONFIRMED: "Your order is confirmed and we're processing your payment.",
        OrderStatus.PAYMENT_PROCESSING: "Your payment is being processed.",
        OrderStatus.PAYMENT_CONFIRMED: "Payment confirmed! We're preparing your order.",
        OrderStatus.PROCESSING: "Your order is being prepared by the seller.",
        OrderStatus.PICKING: "Items are being picked from our warehouse.",
        OrderStatus.PACKED: "Your order has been carefully packed.",
        OrderStatus.READY_FOR_PICKUP: "Your order is ready for carrier pickup.",
        OrderStatus.PICKED_UP: "Your package has been picked up by our delivery partner.",
        OrderStatus.IN_TRANSIT: "Your package is on its way to you.",
        OrderStatus.OUT_FOR_DELIVERY: "Your package is out for delivery today.",
        OrderStatus.DELIVERY_ATTEMPTED: "Delivery was attempted but unsuccessful. We'll try again.",
        OrderStatus.DELIVERED: "Your package has been delivered successfully!",
        OrderStatus.COMPLETED: "Order completed. Thank you for shopping with us!",
        OrderStatus.CANCELLED: "Your order has been cancelled.",
        OrderStatus.RETURNED: "Your order has been returned.",
        OrderStatus.REFUNDED: "Your refund has been processed.",
        OrderStatus.EXCEPTION: "There's an issue with your delivery. We're working to resolve it."
    }

    # Status categories for UI grouping
    STATUS_CATEGORIES = {
        'active': [OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PAYMENT_PROCESSING,
                  OrderStatus.PAYMENT_CONFIRMED, OrderStatus.PROCESSING, OrderStatus.PICKING,
                  OrderStatus.PACKED, OrderStatus.READY_FOR_PICKUP, OrderStatus.PICKED_UP,
                  OrderStatus.IN_TRANSIT, OrderStatus.OUT_FOR_DELIVERY],
        'completed': [OrderStatus.DELIVERED, OrderStatus.COMPLETED],
        'attention': [OrderStatus.DELIVERY_ATTEMPTED, OrderStatus.EXCEPTION],
        'final': [OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.REFUNDED]
    }

    def __init__(self, db: Session):
        self.db = db
        self.notification_service = NotificationService(db)

    async def transition_order_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        changed_by_user_id: Optional[str] = None,
        notes: Optional[str] = None,
        metadata: Optional[Dict] = None,
        auto_notify: bool = True
    ) -> Tuple[bool, str]:
        """
        Transition an order to a new status with validation, history tracking, and notifications

        Returns:
            Tuple[bool, str]: (success, message)
        """
        try:
            # Get the order
            order = self.db.query(Order).filter(Order.id == order_id).first()
            if not order:
                return False, "Order not found"

            old_status = order.status

            # Validate transition
            if not self._is_valid_transition(old_status, new_status):
                return False, f"Invalid status transition from {old_status.value} to {new_status.value}"

            # Update order status and timestamp
            order.status = new_status
            order.status_updated_at = datetime.utcnow()

            # Update specific timestamp fields
            self._update_status_timestamps(order, new_status)

            # Create status history record
            status_history = OrderStatusHistory(
                order_id=order_id,
                old_status=old_status.value if old_status else None,
                new_status=new_status.value,
                changed_by=changed_by_user_id,
                changed_at=datetime.utcnow(),
                notes=notes,
                metadata_json=metadata
            )

            self.db.add(status_history)
            self.db.commit()

            # Send notifications if enabled
            if auto_notify:
                await self._send_status_notification(order, old_status, new_status)

            # Emit order status change event for real-time notifications
            try:
                status_change_event = OrderStatusChangeEvent(
                    order_id=order_id,
                    customer_id=order.customer_id,
                    old_status=old_status.value if old_status else None,
                    new_status=new_status.value,
                    changed_by=changed_by_user_id,
                    notes=notes,
                    estimated_delivery=order.current_estimated_delivery.isoformat() if order.current_estimated_delivery else None
                )
                await event_bus.emit_event(status_change_event)
            except Exception as e:
                logger.warning(f"Failed to emit status change event for order {order_id}: {str(e)}")

            # 🚀 AUTOMATIC DELIVERY REQUEST: Trigger Serrand delivery when order is ready
            try:
                from services.serrand_delivery_service import SerrandDeliveryService
                serrand_service = SerrandDeliveryService(self.db)
                
                if await serrand_service.should_trigger_delivery(order, new_status):
                    logger.info(f"🚚 Automatically requesting delivery for order {order_id}")
                    delivery_result = await serrand_service.create_delivery_request(order)
                    
                    if delivery_result.get("success"):
                        logger.info(f"✅ Delivery requested successfully: {delivery_result.get('tracking_number')}")
                    else:
                        logger.warning(f"⚠️ Failed to request delivery: {delivery_result.get('message')}")
            except ImportError:
                logger.warning("Serrand delivery service not available")
            except Exception as e:
                logger.error(f"Error triggering automatic delivery: {str(e)}", exc_info=True)
                # Don't fail the status update if delivery request fails

            logger.info(f"Order {order_id} status changed from {old_status} to {new_status}")
            return True, "Status updated successfully"

        except Exception as e:
            logger.error(f"Error transitioning order status: {str(e)}")
            self.db.rollback()
            return False, f"Error updating status: {str(e)}"

    def _is_valid_transition(self, current_status: OrderStatus, new_status: OrderStatus) -> bool:
        """Check if a status transition is valid"""
        if current_status is None:
            return new_status == OrderStatus.PENDING

        allowed_transitions = self.STATUS_TRANSITIONS.get(current_status, [])
        return new_status in allowed_transitions

    def _update_status_timestamps(self, order: Order, status: OrderStatus):
        """Update specific timestamp fields based on the new status"""
        now = datetime.utcnow()

        timestamp_mapping = {
            OrderStatus.CONFIRMED: 'confirmed_at',
            OrderStatus.PAYMENT_CONFIRMED: 'payment_confirmed_at',
            OrderStatus.PROCESSING: 'processing_started_at',
            OrderStatus.PACKED: 'packed_at',
            OrderStatus.PICKED_UP: 'picked_up_at',
            OrderStatus.IN_TRANSIT: 'shipped_at',
            OrderStatus.OUT_FOR_DELIVERY: 'out_for_delivery_at',
            OrderStatus.DELIVERED: 'delivered_at',
            OrderStatus.COMPLETED: 'completed_at',
            OrderStatus.CANCELLED: 'cancelled_at'
        }

        field_name = timestamp_mapping.get(status)
        if field_name:
            setattr(order, field_name, now)

    async def _send_status_notification(self, order: Order, old_status: OrderStatus, new_status: OrderStatus):
        """Send notification to customer about status change"""
        try:
            title = f"Order Update: {self.STATUS_DISPLAY_NAMES[new_status]}"
            message = f"Your order #{order.id} is now {self.STATUS_DESCRIPTIONS[new_status]}"

            # Determine notification priority based on status
            priority = NotificationPriority.HIGH if new_status in [
                OrderStatus.DELIVERED, OrderStatus.EXCEPTION, OrderStatus.CANCELLED
            ] else NotificationPriority.MEDIUM

            await self.notification_service.create_notification(
                user_id=order.customer_id,
                title=title,
                message=message,
                notification_type=NotificationType.ORDER_UPDATE,
                priority=priority,
                action_url=f"/my-orders?order_id={order.id}",
                action_label="View Order",
                related_id=order.id,
                related_type="order"
            )

        except Exception as e:
            logger.error(f"Error sending status notification: {str(e)}")

    def get_order_timeline(self, order: Order) -> List[Dict]:
        """Generate a timeline of order progress for frontend display"""
        timeline = []

        # Define the standard order flow
        standard_flow = [
            (OrderStatus.PENDING, 'Order Placed', 'order.created_at'),
            (OrderStatus.CONFIRMED, 'Order Confirmed', 'order.confirmed_at'),
            (OrderStatus.PAYMENT_CONFIRMED, 'Payment Confirmed', 'order.payment_confirmed_at'),
            (OrderStatus.PROCESSING, 'Processing Started', 'order.processing_started_at'),
            (OrderStatus.PACKED, 'Order Packed', 'order.packed_at'),
            (OrderStatus.PICKED_UP, 'Picked Up', 'order.picked_up_at'),
            (OrderStatus.IN_TRANSIT, 'In Transit', 'order.shipped_at'),
            (OrderStatus.OUT_FOR_DELIVERY, 'Out for Delivery', 'order.out_for_delivery_at'),
            (OrderStatus.DELIVERED, 'Delivered', 'order.delivered_at')
        ]

        current_status = order.status

        for status, title, timestamp_field in standard_flow:
            # Get timestamp value
            timestamp = None
            if '.' in timestamp_field:
                obj_name, field_name = timestamp_field.split('.')
                if obj_name == 'order':
                    timestamp = getattr(order, field_name, None)

            # Determine if this step is completed, current, or upcoming
            step_state = self._get_step_state(status, current_status, timestamp)

            timeline.append({
                'status': status.value,
                'title': title,
                'description': self.STATUS_DESCRIPTIONS.get(status, ''),
                'timestamp': timestamp.isoformat() if timestamp else None,
                'state': step_state,  # 'completed', 'current', 'upcoming'
                'icon': self._get_status_icon(status)
            })

        return timeline

    def _get_step_state(self, step_status: OrderStatus, current_status: OrderStatus, timestamp: Optional[datetime]) -> str:
        """Determine if a timeline step is completed, current, or upcoming"""
        if timestamp:
            return 'completed'
        elif step_status == current_status:
            return 'current'
        else:
            # Check if this step comes before the current status in the flow
            status_order = [
                OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PAYMENT_CONFIRMED,
                OrderStatus.PROCESSING, OrderStatus.PACKED, OrderStatus.PICKED_UP,
                OrderStatus.IN_TRANSIT, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED
            ]

            try:
                step_index = status_order.index(step_status)
                current_index = status_order.index(current_status)
                return 'completed' if step_index < current_index else 'upcoming'
            except ValueError:
                return 'upcoming'

    def _get_status_icon(self, status: OrderStatus) -> str:
        """Get icon name for each status"""
        icon_mapping = {
            OrderStatus.PENDING: 'Clock',
            OrderStatus.CONFIRMED: 'CheckCircle',
            OrderStatus.PAYMENT_CONFIRMED: 'CreditCard',
            OrderStatus.PROCESSING: 'Package',
            OrderStatus.PACKED: 'Box',
            OrderStatus.PICKED_UP: 'Truck',
            OrderStatus.IN_TRANSIT: 'MapPin',
            OrderStatus.OUT_FOR_DELIVERY: 'Navigation',
            OrderStatus.DELIVERED: 'Home',
            OrderStatus.CANCELLED: 'XCircle',
            OrderStatus.EXCEPTION: 'AlertTriangle'
        }
        return icon_mapping.get(status, 'Circle')

    def get_estimated_delivery_update(self, order: Order) -> Optional[datetime]:
        """Calculate updated delivery estimate based on current status and historical data"""
        if not order.current_estimated_delivery:
            return order.estimated_delivery_date

        # Add buffer time based on current status
        status_buffers = {
            OrderStatus.PENDING: timedelta(days=0),
            OrderStatus.CONFIRMED: timedelta(hours=2),
            OrderStatus.PROCESSING: timedelta(hours=6),
            OrderStatus.PACKED: timedelta(hours=12),
            OrderStatus.IN_TRANSIT: timedelta(hours=24),
            OrderStatus.OUT_FOR_DELIVERY: timedelta(hours=4)
        }

        buffer = status_buffers.get(order.status, timedelta(0))
        return order.current_estimated_delivery + buffer

    def get_next_expected_status(self, current_status: OrderStatus) -> Optional[OrderStatus]:
        """Get the next expected status in the normal flow"""
        normal_flow = [
            OrderStatus.PENDING, OrderStatus.CONFIRMED, OrderStatus.PAYMENT_CONFIRMED,
            OrderStatus.PROCESSING, OrderStatus.PACKED, OrderStatus.PICKED_UP,
            OrderStatus.IN_TRANSIT, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED
        ]

        try:
            current_index = normal_flow.index(current_status)
            if current_index < len(normal_flow) - 1:
                return normal_flow[current_index + 1]
        except ValueError:
            pass

        return None