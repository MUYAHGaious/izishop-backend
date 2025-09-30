"""
Payment Distribution Service for Multi-Vendor Orders
Integrates with existing Tranzak payment system to handle commission distribution
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal
import uuid
import logging
from sqlalchemy.orm import Session

from models.order import Order, OrderStatus, PaymentStatus
from models.user import User
from models.shop import Shop
from models.notification import Notification, NotificationType, NotificationPriority

logger = logging.getLogger(__name__)

class PaymentDistributionService:
    """Service for distributing payments among vendors in multi-vendor orders"""
    
    def __init__(self, db: Session):
        self.db = db
        self.platform_commission_rate = Decimal('0.05')  # 5% platform commission
        self.payment_processing_fee_rate = Decimal('0.029')  # 2.9% payment processing fee
    
    async def distribute_multi_vendor_payment(
        self,
        master_order_id: str,
        payment_reference: str,
        total_payment_amount: Decimal
    ) -> Dict[str, Any]:
        """
        Distribute payment from master order to vendor orders
        
        Args:
            master_order_id: The master order ID
            payment_reference: Payment transaction reference
            total_payment_amount: Total amount paid by customer
            
        Returns:
            Dictionary with distribution results
        """
        try:
            logger.info(f"Distributing payment for master order {master_order_id}")
            
            # Get master order
            master_order = self.db.query(Order).filter(Order.id == master_order_id).first()
            if not master_order:
                logger.error(f"Master order {master_order_id} not found")
                return {"error": "Master order not found"}
            
            # Get vendor orders for this master order
            vendor_orders = self.db.query(Order).filter(
                Order.notes.like(f"%master order {master_order_id}%")
            ).all()
            
            if not vendor_orders:
                logger.error(f"No vendor orders found for master order {master_order_id}")
                return {"error": "No vendor orders found"}
            
            # Update master order payment status
            master_order.payment_status = PaymentStatus.PAID
            master_order.updated_at = datetime.now(timezone.utc)
            
            # Distribute to vendors
            distribution_results = []
            total_vendor_amount = Decimal('0.00')
            
            for vendor_order in vendor_orders:
                # Calculate vendor-specific fees
                vendor_amount = Decimal(str(vendor_order.total_amount))
                vendor_commission = vendor_amount * self.platform_commission_rate
                vendor_processing_fee = vendor_amount * self.payment_processing_fee_rate
                
                # Calculate net amount to vendor
                net_vendor_amount = vendor_amount - vendor_commission - vendor_processing_fee
                
                # Update vendor order payment status
                vendor_order.payment_status = PaymentStatus.PAID
                vendor_order.updated_at = datetime.now(timezone.utc)
                
                # Create payment distribution record (we'll add this model later)
                distribution_record = {
                    'vendor_order_id': vendor_order.id,
                    'vendor_id': vendor_order.shop_id,
                    'gross_amount': float(vendor_amount),
                    'platform_commission': float(vendor_commission),
                    'processing_fee': float(vendor_processing_fee),
                    'net_amount': float(net_vendor_amount),
                    'payment_reference': payment_reference,
                    'distribution_date': datetime.now(timezone.utc).isoformat()
                }
                
                distribution_results.append(distribution_record)
                total_vendor_amount += net_vendor_amount
                
                # Send payment notification to vendor
                await self._send_payment_notification(vendor_order, distribution_record)
            
            # Commit all changes
            self.db.commit()
            
            logger.info(f"Successfully distributed payment for master order {master_order_id}")
            
            return {
                'master_order_id': master_order_id,
                'total_payment_amount': float(total_payment_amount),
                'platform_commission': float(total_payment_amount * self.platform_commission_rate),
                'payment_processing_fee': float(total_payment_amount * self.payment_processing_fee_rate),
                'total_vendor_amount': float(total_vendor_amount),
                'vendor_distributions': distribution_results,
                'payment_reference': payment_reference,
                'distribution_date': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to distribute payment: {str(e)}")
            raise
    
    async def _send_payment_notification(
        self,
        vendor_order: Order,
        distribution_record: Dict[str, Any]
    ) -> None:
        """Send payment notification to vendor"""
        try:
            # Get vendor/shop owner
            shop = self.db.query(Shop).filter(Shop.id == vendor_order.shop_id).first()
            if not shop:
                return
            
            vendor = self.db.query(User).filter(User.id == shop.owner_id).first()
            if not vendor:
                return
            
            # Create payment notification
            notification = Notification(
                user_id=vendor.id,
                type=NotificationType.PAYMENT,
                title="💰 Payment Received!",
                message=f"""Great news! You've received a payment for your order.

💳 PAYMENT DETAILS:
• Order ID: {vendor_order.id}
• Gross Amount: ${distribution_record['gross_amount']:.2f}
• Platform Commission (5%): ${distribution_record['platform_commission']:.2f}
• Processing Fee (2.9%): ${distribution_record['processing_fee']:.2f}
• Net Amount: ${distribution_record['net_amount']:.2f}

📊 COMMISSION BREAKDOWN:
• Platform Fee: 5% of order value
• Payment Processing: 2.9% of order value
• Your Earnings: ${distribution_record['net_amount']:.2f}

🚀 NEXT STEPS:
1. Review your earnings in the dashboard
2. Process the order for shipping
3. Update order status when shipped

Need help? Contact our support team anytime!

IziShopin Team 🚀""",
                related_id=vendor_order.id,
                related_type="payment_received",
                priority=NotificationPriority.HIGH,
                action_url=f"/shop-owner-dashboard/orders/{vendor_order.id}",
                action_label="View Order",
                icon="CreditCard"
            )
            
            self.db.add(notification)
            logger.info(f"Created payment notification for vendor {vendor.email}")
            
        except Exception as e:
            logger.error(f"Failed to send payment notification: {str(e)}")
    
    def calculate_commission(
        self,
        order_amount: Decimal,
        vendor_tier: str = "standard"
    ) -> Dict[str, Decimal]:
        """Calculate commission based on vendor tier"""
        # Different commission rates based on vendor tier
        commission_rates = {
            "standard": Decimal('0.05'),    # 5%
            "premium": Decimal('0.03'),     # 3%
            "enterprise": Decimal('0.02')    # 2%
        }
        
        commission_rate = commission_rates.get(vendor_tier, Decimal('0.05'))
        commission_amount = order_amount * commission_rate
        
        return {
            'rate': commission_rate,
            'amount': commission_amount,
            'net_amount': order_amount - commission_amount
        }
    
    def get_vendor_earnings_summary(
        self,
        vendor_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get vendor earnings summary (placeholder for future implementation)"""
        # This would query payment distribution records
        # For now, return placeholder data
        return {
            'total_orders': 0,
            'total_gross_amount': 0.0,
            'total_platform_commission': 0.0,
            'total_processing_fees': 0.0,
            'total_net_earnings': 0.0,
            'average_order_value': 0.0,
            'commission_rate': float(self.platform_commission_rate),
            'processing_fee_rate': float(self.payment_processing_fee_rate)
        }
