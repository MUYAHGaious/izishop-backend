"""
Serrand Delivery Service
Automatically creates delivery requests with Serrand when orders are ready for delivery
"""
import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models.order import Order, OrderStatus
from models.shop import Shop
from models.user import User
from models.delivery_tracking import DeliveryTracking
from decimal import Decimal
import uuid
import httpx

logger = logging.getLogger(__name__)

# Serrand API Configuration
SERRAND_API_URL = os.getenv('SERRAND_API_URL', 'https://api.serrand.com')
SERRAND_API_KEY = os.getenv('SERRAND_API_KEY', '')
SERRAND_API_SECRET = os.getenv('SERRAND_API_SECRET', '')
SERRAND_ENABLED = os.getenv('SERRAND_ENABLED', 'true').lower() == 'true'
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')


class SerrandDeliveryService:
    """Service for automatically creating delivery requests with Serrand"""
    
    def __init__(self, db: Session):
        self.db = db
        
    async def get_serrand_headers(self) -> Dict[str, str]:
        """Get authentication headers for Serrand API"""
        return {
            "Authorization": f"Bearer {SERRAND_API_KEY}",
            "Content-Type": "application/json",
            "X-API-Secret": SERRAND_API_SECRET,
            "X-API-Key": SERRAND_API_KEY
        }
    
    async def create_delivery_request(self, order: Order) -> Dict[str, Any]:
        """
        Automatically create a delivery request with Serrand for an order
        
        Args:
            order: The Order object that needs delivery
            
        Returns:
            Dict with delivery request result
        """
        if not SERRAND_ENABLED:
            logger.warning("Serrand delivery service is disabled")
            return {"success": False, "message": "Serrand service disabled"}
        
        try:
            # Check if delivery already requested
            existing_tracking = self.db.query(DeliveryTracking).filter(
                DeliveryTracking.order_id == order.id
            ).first()
            
            if existing_tracking:
                logger.info(f"Delivery already requested for order {order.id}")
                return {
                    "success": True,
                    "message": "Delivery already requested",
                    "tracking_id": existing_tracking.id,
                    "partner_delivery_id": existing_tracking.partner_delivery_id
                }
            
            # Get shop and seller information
            shop = self.db.query(Shop).filter(Shop.id == order.shop_id).first()
            if not shop:
                logger.error(f"Shop not found for order {order.id}")
                return {"success": False, "message": "Shop not found"}
            
            seller = self.db.query(User).filter(User.id == shop.owner_id).first()
            if not seller:
                logger.error(f"Seller not found for order {order.id}")
                return {"success": False, "message": "Seller not found"}
            
            # Get customer information
            customer = self.db.query(User).filter(User.id == order.customer_id).first()
            if not customer:
                logger.error(f"Customer not found for order {order.id}")
                return {"success": False, "message": "Customer not found"}
            
            # Extract pickup location (from shop/seller)
            pickup_location = self._extract_pickup_location(shop, seller)
            
            # Extract delivery location (from order shipping address)
            delivery_location = self._extract_delivery_location(order, customer)
            
            # Prepare delivery request payload for Serrand
            delivery_request = {
                "external_order_id": order.id,
                "pickup_location": pickup_location,
                "delivery_location": delivery_location,
                "package_details": {
                    "weight": 1.0,  # Default weight, can be enhanced with product weights
                    "dimensions": {
                        "length": 10,
                        "width": 10,
                        "height": 10
                    },
                    "value": float(order.total_amount),
                    "description": f"IziShop Order #{order.id}"
                },
                "delivery_preferences": {
                    "priority": "standard",  # standard, express, same_day
                    "requires_signature": True,
                    "fragile": False
                },
                "webhook_url": f"{BASE_URL}/api/delivery/webhooks",
                "webhook_secret": os.getenv('SERRAND_WEBHOOK_SECRET', ''),
                "metadata": {
                    "order_id": order.id,
                    "shop_id": shop.id,
                    "customer_id": customer.id,
                    "platform": "izishop"
                }
            }
            
            # Send request to Serrand API
            headers = await self.get_serrand_headers()
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.post(
                        f"{SERRAND_API_URL}/deliveries/create",
                        json=delivery_request,
                        headers=headers
                    )
                    
                    if response.status_code not in [200, 201]:
                        logger.error(f"Serrand API error: {response.status_code} - {response.text}")
                        return {
                            "success": False,
                            "message": f"Failed to create delivery request: {response.text}",
                            "status_code": response.status_code
                        }
                    
                    partner_response = response.json()
                    
                except httpx.TimeoutException:
                    logger.error("Serrand API timeout")
                    return {"success": False, "message": "Serrand API timeout"}
                except Exception as e:
                    logger.error(f"Error calling Serrand API: {str(e)}")
                    return {"success": False, "message": f"API error: {str(e)}"}
            
            # Create delivery tracking record
            tracking = DeliveryTracking(
                id=str(uuid.uuid4()),
                order_id=order.id,
                partner_delivery_id=partner_response.get('delivery_id') or partner_response.get('id'),
                partner_tracking_number=partner_response.get('tracking_number') or partner_response.get('tracking_id'),
                status='requested',
                pickup_location=pickup_location,
                delivery_location=delivery_location,
                estimated_delivery_fee=Decimal(str(partner_response.get('estimated_cost', 0))),
                estimated_delivery_time=self._parse_delivery_time(partner_response.get('estimated_delivery_time')),
                created_at=datetime.now(timezone.utc)
            )
            
            self.db.add(tracking)
            
            # Update order with tracking number
            order.tracking_number = tracking.partner_tracking_number
            order.carrier = "Serrand"
            
            self.db.commit()
            self.db.refresh(tracking)
            
            logger.info(f"✅ Delivery requested with Serrand for order {order.id}: {tracking.partner_delivery_id}")
            
            return {
                "success": True,
                "message": "Delivery request created successfully",
                "tracking_id": tracking.id,
                "partner_delivery_id": tracking.partner_delivery_id,
                "tracking_number": tracking.partner_tracking_number,
                "estimated_cost": float(tracking.estimated_delivery_fee or 0),
                "estimated_delivery_time": tracking.estimated_delivery_time.isoformat() if tracking.estimated_delivery_time else None
            }
            
        except Exception as e:
            logger.error(f"Error creating delivery request: {str(e)}", exc_info=True)
            self.db.rollback()
            return {"success": False, "message": f"Error: {str(e)}"}
    
    def _extract_pickup_location(self, shop: Shop, seller: User) -> Dict[str, Any]:
        """Extract pickup location from shop and seller information"""
        # Try to get coordinates from shop if available
        coordinates = None
        if shop.coordinates:
            try:
                import json
                coordinates = json.loads(shop.coordinates)
            except:
                pass
        
        return {
            "address": shop.address or "Shop Address",
            "latitude": coordinates.get('lat') if coordinates else None,
            "longitude": coordinates.get('lng') if coordinates else None,
            "contact_name": f"{seller.first_name} {seller.last_name}",
            "contact_phone": seller.phone or shop.phone,
            "special_instructions": "Please call before pickup"
        }
    
    def _extract_delivery_location(self, order: Order, customer: User) -> Dict[str, Any]:
        """Extract delivery location from order shipping address"""
        # Parse shipping address (assuming it contains address info)
        # In production, you might want to parse this more intelligently
        # or store lat/lng separately
        
        return {
            "address": order.shipping_address or "Delivery Address",
            "latitude": None,  # Can be enhanced with geocoding
            "longitude": None,  # Can be enhanced with geocoding
            "contact_name": f"{customer.first_name} {customer.last_name}",
            "contact_phone": customer.phone,
            "special_instructions": order.delivery_instructions or "Please call before delivery"
        }
    
    def _parse_delivery_time(self, time_str: Optional[str]) -> Optional[datetime]:
        """Parse delivery time string from Serrand response"""
        if not time_str:
            return None
        
        try:
            # Try ISO format
            return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except:
            try:
                # Try other formats
                return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            except:
                logger.warning(f"Could not parse delivery time: {time_str}")
                return None
    
    async def should_trigger_delivery(self, order: Order, new_status: OrderStatus) -> bool:
        """
        Determine if delivery should be automatically triggered
        
        Triggers when order reaches PACKED or READY_FOR_PICKUP status
        """
        # Only trigger for these statuses
        trigger_statuses = [OrderStatus.PACKED, OrderStatus.READY_FOR_PICKUP]
        
        if new_status not in trigger_statuses:
            return False
        
        # Check if payment is confirmed
        if order.payment_status.value != 'paid':
            logger.info(f"Order {order.id} payment not confirmed, skipping delivery request")
            return False
        
        # Check if delivery already requested
        existing_tracking = self.db.query(DeliveryTracking).filter(
            DeliveryTracking.order_id == order.id
        ).first()
        
        if existing_tracking:
            logger.info(f"Delivery already requested for order {order.id}")
            return False
        
        return True

