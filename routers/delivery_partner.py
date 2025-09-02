"""
External Delivery Partner Integration
Handles communication with third-party delivery service
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.order import Order
from models.delivery_tracking import DeliveryTracking
import httpx
import json
import os
from decimal import Decimal
import uuid

router = APIRouter(prefix="/api/delivery", tags=["delivery-integration"])
logger = logging.getLogger(__name__)

# Configuration for delivery partner API
DELIVERY_PARTNER_API_URL = os.getenv('DELIVERY_PARTNER_API_URL', 'https://api.delivery-partner.com')
DELIVERY_PARTNER_API_KEY = os.getenv('DELIVERY_PARTNER_API_KEY')
DELIVERY_PARTNER_SECRET = os.getenv('DELIVERY_PARTNER_SECRET')
DELIVERY_WEBHOOK_SECRET = os.getenv('DELIVERY_WEBHOOK_SECRET')

async def get_delivery_partner_headers():
    """Get headers for delivery partner API requests"""
    return {
        "Authorization": f"Bearer {DELIVERY_PARTNER_API_KEY}",
        "Content-Type": "application/json",
        "X-API-Secret": DELIVERY_PARTNER_SECRET
    }

@router.post("/request-delivery/{order_id}")
async def request_delivery(
    order_id: str,
    delivery_details: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send delivery request to external partner"""
    try:
        # Get the order
        order = db.query(Order).filter(Order.id == order_id).first()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Verify user can request delivery for this order
        if order.customer_id != current_user.id and current_user.role not in ['ADMIN', 'SHOP_OWNER']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to request delivery for this order"
            )
        
        # Prepare delivery request payload
        delivery_request = {
            "external_order_id": order_id,
            "pickup_location": {
                "address": delivery_details.get('pickup_address'),
                "latitude": delivery_details.get('pickup_lat'),
                "longitude": delivery_details.get('pickup_lng'),
                "contact_name": delivery_details.get('pickup_contact_name'),
                "contact_phone": delivery_details.get('pickup_contact_phone'),
                "special_instructions": delivery_details.get('pickup_instructions')
            },
            "delivery_location": {
                "address": delivery_details.get('delivery_address'),
                "latitude": delivery_details.get('delivery_lat'),
                "longitude": delivery_details.get('delivery_lng'),
                "contact_name": delivery_details.get('delivery_contact_name'),
                "contact_phone": delivery_details.get('delivery_contact_phone'),
                "special_instructions": delivery_details.get('delivery_instructions')
            },
            "package_details": {
                "weight": delivery_details.get('package_weight'),
                "dimensions": delivery_details.get('package_dimensions'),
                "value": float(order.total_amount),
                "description": delivery_details.get('package_description', f"IziShopin Order #{order_id}")
            },
            "delivery_preferences": {
                "priority": delivery_details.get('priority', 'standard'),  # standard, express, same_day
                "preferred_time": delivery_details.get('preferred_delivery_time'),
                "fragile": delivery_details.get('fragile', False),
                "requires_signature": delivery_details.get('requires_signature', True)
            },
            "webhook_url": f"{os.getenv('BASE_URL', 'http://localhost:8000')}/api/delivery/webhooks",
            "webhook_secret": DELIVERY_WEBHOOK_SECRET
        }
        
        # Send request to delivery partner
        headers = await get_delivery_partner_headers()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DELIVERY_PARTNER_API_URL}/deliveries/create",
                json=delivery_request,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code not in [200, 201]:
                logger.error(f"Delivery partner API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to create delivery request: {response.text}"
                )
            
            partner_response = response.json()
            
        # Create delivery tracking record
        tracking = DeliveryTracking(
            id=str(uuid.uuid4()),
            order_id=order_id,
            partner_delivery_id=partner_response.get('delivery_id'),
            partner_tracking_number=partner_response.get('tracking_number'),
            status='requested',
            pickup_location=delivery_request['pickup_location'],
            delivery_location=delivery_request['delivery_location'],
            estimated_delivery_fee=Decimal(str(partner_response.get('estimated_cost', 0))),
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(tracking)
        
        # Update order status
        order.delivery_status = 'requested'
        order.delivery_tracking_number = partner_response.get('tracking_number')
        
        db.commit()
        db.refresh(tracking)
        
        logger.info(f"Delivery requested for order {order_id}: {partner_response.get('delivery_id')}")
        
        return {
            "message": "Delivery request sent successfully",
            "tracking_id": tracking.id,
            "partner_delivery_id": partner_response.get('delivery_id'),
            "tracking_number": partner_response.get('tracking_number'),
            "estimated_cost": partner_response.get('estimated_cost'),
            "estimated_delivery_time": partner_response.get('estimated_delivery_time')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error requesting delivery: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to request delivery"
        )

@router.get("/quote")
async def get_delivery_quote(
    pickup_lat: float,
    pickup_lng: float,
    delivery_lat: float,
    delivery_lng: float,
    package_weight: Optional[float] = 1.0,
    priority: Optional[str] = "standard"
):
    """Get delivery cost quote from partner API"""
    try:
        quote_request = {
            "pickup_location": {
                "latitude": pickup_lat,
                "longitude": pickup_lng
            },
            "delivery_location": {
                "latitude": delivery_lat,
                "longitude": delivery_lng
            },
            "package_details": {
                "weight": package_weight
            },
            "delivery_preferences": {
                "priority": priority
            }
        }
        
        headers = await get_delivery_partner_headers()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DELIVERY_PARTNER_API_URL}/deliveries/quote",
                json=quote_request,
                headers=headers,
                timeout=15.0
            )
            
            if response.status_code != 200:
                logger.error(f"Quote API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to get delivery quote"
                )
            
            quote_data = response.json()
            
        return {
            "estimated_cost": quote_data.get('cost'),
            "estimated_distance": quote_data.get('distance_km'),
            "estimated_duration": quote_data.get('duration_minutes'),
            "delivery_options": quote_data.get('available_options', []),
            "currency": quote_data.get('currency', 'USD')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting delivery quote: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get delivery quote"
        )

@router.get("/track/{tracking_number}")
async def track_delivery(
    tracking_number: str,
    db: Session = Depends(get_db)
):
    """Track delivery status using partner's tracking API"""
    try:
        # Get internal tracking record
        tracking = db.query(DeliveryTracking).filter(
            DeliveryTracking.partner_tracking_number == tracking_number
        ).first()
        
        if not tracking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tracking number not found"
            )
        
        # Get latest status from partner API
        headers = await get_delivery_partner_headers()
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{DELIVERY_PARTNER_API_URL}/deliveries/{tracking.partner_delivery_id}/track",
                headers=headers,
                timeout=15.0
            )
            
            if response.status_code != 200:
                logger.warning(f"Partner tracking API error: {response.status_code}")
                # Return cached data if partner API fails
                return {
                    "tracking_number": tracking_number,
                    "status": tracking.status,
                    "current_location": tracking.current_location,
                    "estimated_delivery": tracking.estimated_delivery_time.isoformat() if tracking.estimated_delivery_time else None,
                    "delivery_history": tracking.status_history or [],
                    "last_updated": tracking.updated_at.isoformat(),
                    "source": "cached"
                }
            
            partner_data = response.json()
            
        # Update local tracking record
        tracking.status = partner_data.get('status', tracking.status)
        tracking.current_location = partner_data.get('current_location')
        tracking.estimated_delivery_time = partner_data.get('estimated_delivery_time')
        tracking.status_history = partner_data.get('status_history', [])
        tracking.updated_at = datetime.now(timezone.utc)
        
        if partner_data.get('status') == 'delivered':
            tracking.delivered_at = datetime.now(timezone.utc)
            
            # Update order status
            order = db.query(Order).filter(Order.id == tracking.order_id).first()
            if order:
                order.delivery_status = 'delivered'
        
        db.commit()
        
        return {
            "tracking_number": tracking_number,
            "status": tracking.status,
            "current_location": tracking.current_location,
            "estimated_delivery": tracking.estimated_delivery_time.isoformat() if tracking.estimated_delivery_time else None,
            "delivery_history": tracking.status_history or [],
            "last_updated": tracking.updated_at.isoformat(),
            "source": "live"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking delivery: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to track delivery"
        )

@router.post("/webhooks")
async def delivery_webhooks(
    request: Request,
    db: Session = Depends(get_db)
):
    """Receive delivery status updates from partner API"""
    try:
        payload = await request.body()
        webhook_data = json.loads(payload)
        
        # Verify webhook signature (implement based on partner's requirements)
        webhook_signature = request.headers.get('X-Webhook-Signature')
        if not webhook_signature:
            raise HTTPException(status_code=400, detail="Missing webhook signature")
        
        # TODO: Implement signature verification based on partner's method
        # if not verify_webhook_signature(payload, webhook_signature, DELIVERY_WEBHOOK_SECRET):
        #     raise HTTPException(status_code=400, detail="Invalid webhook signature")
        
        event_type = webhook_data.get('event')
        delivery_data = webhook_data.get('data', {})
        partner_delivery_id = delivery_data.get('delivery_id')
        
        if not partner_delivery_id:
            raise HTTPException(status_code=400, detail="Missing delivery ID")
        
        # Find tracking record
        tracking = db.query(DeliveryTracking).filter(
            DeliveryTracking.partner_delivery_id == partner_delivery_id
        ).first()
        
        if not tracking:
            logger.warning(f"Received webhook for unknown delivery: {partner_delivery_id}")
            return JSONResponse(content={"status": "ignored", "reason": "unknown_delivery"})
        
        # Update tracking based on event type
        if event_type == 'delivery.status_updated':
            new_status = delivery_data.get('status')
            tracking.status = new_status
            tracking.current_location = delivery_data.get('location')
            tracking.estimated_delivery_time = delivery_data.get('estimated_delivery_time')
            
            # Add to status history
            status_history = tracking.status_history or []
            status_history.append({
                "status": new_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "location": delivery_data.get('location'),
                "notes": delivery_data.get('notes')
            })
            tracking.status_history = status_history
            tracking.updated_at = datetime.now(timezone.utc)
            
            # Update order if delivered
            if new_status == 'delivered':
                tracking.delivered_at = datetime.now(timezone.utc)
                order = db.query(Order).filter(Order.id == tracking.order_id).first()
                if order:
                    order.delivery_status = 'delivered'
                    order.delivered_at = datetime.now(timezone.utc)
            
        elif event_type == 'delivery.driver_assigned':
            tracking.driver_info = {
                "name": delivery_data.get('driver_name'),
                "phone": delivery_data.get('driver_phone'),
                "vehicle": delivery_data.get('vehicle_info'),
                "photo": delivery_data.get('driver_photo_url')
            }
            
        elif event_type == 'delivery.exception':
            tracking.status = 'exception'
            tracking.exception_reason = delivery_data.get('reason')
            tracking.exception_details = delivery_data.get('details')
            
        db.commit()
        
        logger.info(f"Processed delivery webhook: {event_type} for {partner_delivery_id}")
        
        # TODO: Send real-time updates to customers via WebSocket
        # await notify_customer_delivery_update(tracking.order_id, tracking.status)
        
        return JSONResponse(content={"status": "processed", "event": event_type})
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in delivery webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    except Exception as e:
        logger.error(f"Error processing delivery webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")

@router.get("/my-deliveries")
async def get_my_deliveries(
    status_filter: Optional[str] = None,
    limit: int = 20,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's delivery history"""
    try:
        # Get orders for the current user
        orders_query = db.query(Order).filter(Order.customer_id == current_user.id)
        
        # Get delivery trackings for user's orders
        trackings_query = db.query(DeliveryTracking).join(Order).filter(
            Order.customer_id == current_user.id
        )
        
        if status_filter:
            trackings_query = trackings_query.filter(DeliveryTracking.status == status_filter)
        
        trackings = trackings_query.order_by(desc(DeliveryTracking.created_at)).offset(skip).limit(limit).all()
        
        deliveries = []
        for tracking in trackings:
            order = db.query(Order).filter(Order.id == tracking.order_id).first()
            
            deliveries.append({
                "tracking_id": tracking.id,
                "order_id": tracking.order_id,
                "tracking_number": tracking.partner_tracking_number,
                "status": tracking.status,
                "pickup_location": tracking.pickup_location,
                "delivery_location": tracking.delivery_location,
                "current_location": tracking.current_location,
                "estimated_delivery_fee": float(tracking.estimated_delivery_fee or 0),
                "estimated_delivery_time": tracking.estimated_delivery_time.isoformat() if tracking.estimated_delivery_time else None,
                "delivered_at": tracking.delivered_at.isoformat() if tracking.delivered_at else None,
                "driver_info": tracking.driver_info,
                "status_history": tracking.status_history or [],
                "created_at": tracking.created_at.isoformat(),
                "order_total": float(order.total_amount) if order else 0
            })
        
        return {
            "deliveries": deliveries,
            "total": len(deliveries)
        }
        
    except Exception as e:
        logger.error(f"Error fetching user deliveries: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch deliveries"
        )

@router.post("/cancel/{tracking_id}")
async def cancel_delivery(
    tracking_id: str,
    reason: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a delivery request"""
    try:
        # Get tracking record
        tracking = db.query(DeliveryTracking).join(Order).filter(
            and_(
                DeliveryTracking.id == tracking_id,
                Order.customer_id == current_user.id
            )
        ).first()
        
        if not tracking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Delivery not found or not authorized"
            )
        
        if tracking.status in ['delivered', 'cancelled']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel delivery with status: {tracking.status}"
            )
        
        # Send cancellation to partner API
        headers = await get_delivery_partner_headers()
        cancel_data = {"reason": reason, "requested_by": "customer"}
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{DELIVERY_PARTNER_API_URL}/deliveries/{tracking.partner_delivery_id}/cancel",
                json=cancel_data,
                headers=headers,
                timeout=15.0
            )
            
            if response.status_code not in [200, 204]:
                logger.warning(f"Partner cancellation failed: {response.status_code}")
                # Continue with local cancellation even if partner API fails
        
        # Update local tracking
        tracking.status = 'cancelled'
        tracking.cancellation_reason = reason
        tracking.cancelled_at = datetime.now(timezone.utc)
        
        # Update order
        order = db.query(Order).filter(Order.id == tracking.order_id).first()
        if order:
            order.delivery_status = 'cancelled'
        
        db.commit()
        
        logger.info(f"Delivery {tracking_id} cancelled by customer")
        
        return {
            "message": "Delivery cancelled successfully",
            "tracking_id": tracking_id,
            "status": "cancelled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error cancelling delivery: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel delivery"
        )