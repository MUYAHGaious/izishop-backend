"""
Tranzak webhooks and subscription management for IziShopin
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.shop import Shop
from models.subscription import Subscription
import httpx
import json
import os
from typing import Dict, Any

# Configure Tranzak
TRANZAK_BASE_URL = os.getenv('TRANZAK_BASE_URL', 'https://sandbox.dsapi.tranzak.me')  # Default to sandbox
TRANZAK_APP_ID = os.getenv('TRANZAK_APP_ID')
TRANZAK_APP_KEY = os.getenv('TRANZAK_APP_KEY')
TRANZAK_WEBHOOK_SECRET = os.getenv('TRANZAK_WEBHOOK_SECRET')

router = APIRouter(prefix="/api/tranzak", tags=["tranzak"])
logger = logging.getLogger(__name__)

async def get_tranzak_token(scope: str = "collections") -> str:
    """Get authentication token from Tranzak API"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TRANZAK_BASE_URL}/auth/token",
                json={
                    "appId": TRANZAK_APP_ID,
                    "appKey": TRANZAK_APP_KEY,
                    "scope": scope
                }
            )
            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to authenticate with Tranzak"
                )
            return response.json()["data"]["token"]
    except Exception as e:
        logger.error(f"Error getting Tranzak token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment service authentication failed"
        )

@router.post("/create-shop-subscription")
async def create_shop_subscription(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create Tranzak payment request for shop owner subscription"""
    try:
        # Check if user already has an active subscription
        existing_sub = db.query(Subscription).filter(
            Subscription.user_id == current_user.id,
            Subscription.status.in_(['active', 'trialing'])
        ).first()
        
        if existing_sub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has an active subscription"
            )
        
        # Get Tranzak authentication token
        token = await get_tranzak_token()
        
        # Create payment request
        base_url = request.url.scheme + "://" + request.url.netloc
        
        payment_data = {
            "amount": 29.99,  # $29.99 monthly fee
            "currencyCode": "USD",
            "description": "IziShopin Shop Owner Subscription - Monthly Plan",
            "customData": {
                "user_id": current_user.id,
                "plan_type": "shop_owner",
                "monthly_fee": "29.99",
                "trial_days": "7"
            },
            "payerNote": f"Monthly subscription for {current_user.first_name} {current_user.last_name}",
            "returnUrl": f"{base_url}/settings?upgrade=success",
            "cancelUrl": f"{base_url}/settings?upgrade=cancelled",
            "webhook": f"{base_url}/api/tranzak/webhooks"
        }
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TRANZAK_BASE_URL}/payment/request",
                json=payment_data,
                headers=headers
            )
            
            if response.status_code != 201:
                logger.error(f"Tranzak API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create payment request"
                )
            
            payment_response = response.json()
            logger.info(f"Created Tranzak payment request {payment_response['data']['requestId']} for user {current_user.id}")
            
            return {
                'payment_url': payment_response['data']['paymentAuthUrl'],
                'request_id': payment_response['data']['requestId'],
                'amount': payment_data['amount'],
                'currency': payment_data['currencyCode']
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating shop subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription payment"
        )


@router.post("/webhooks")
async def tranzak_webhooks(request: Request, db: Session = Depends(get_db)):
    """Handle Tranzak webhook events"""
    try:
        payload = await request.body()
        webhook_data = json.loads(payload)
        
        # Basic webhook validation (implement signature verification as needed)
        if not webhook_data.get('data'):
            raise HTTPException(status_code=400, detail="Invalid webhook payload")
        
        event_type = webhook_data.get('event', 'unknown')
        transaction_data = webhook_data['data']
        
        logger.info(f"Received Tranzak webhook: {event_type}")
        
        # Handle different event types based on Tranzak documentation
        if event_type == 'PAYMENT_SUCCESSFUL' or transaction_data.get('status') == 'SUCCESSFUL':
            await handle_payment_successful(transaction_data, db)
            
        elif event_type == 'PAYMENT_FAILED' or transaction_data.get('status') == 'FAILED':
            await handle_payment_failed_tranzak(transaction_data, db)
            
        elif event_type == 'PAYMENT_PENDING' or transaction_data.get('status') == 'PENDING':
            await handle_payment_pending(transaction_data, db)
            
        elif event_type == 'PAYMENT_CANCELLED' or transaction_data.get('status') == 'CANCELLED':
            await handle_payment_cancelled(transaction_data, db)
            
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
        
        return JSONResponse(content={"status": "received", "message": "Webhook processed successfully"})
        
    except ValueError as e:
        logger.error(f"Invalid JSON payload in webhook: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    except Exception as e:
        logger.error(f"Error processing Tranzak webhook: {str(e)}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


async def handle_payment_successful(transaction_data, db: Session):
    """Handle successful payment completion"""
    try:
        custom_data = transaction_data.get('customData', {})
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in transaction customData")
            return
            
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for payment completion")
            return
            
        logger.info(f"Payment successful for user {user_id}, upgrading to SHOP_OWNER")
        
        # Upgrade user role
        user.role = 'SHOP_OWNER'
        user.role_upgraded_at = datetime.now(timezone.utc)
        
        # Create subscription record
        subscription = Subscription(
            user_id=user_id,
            plan_type='shop_owner',
            status='active',
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
            monthly_fee=29.99,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=7),
            tranzak_request_id=transaction_data.get('requestId')
        )
        
        db.add(subscription)
        
        # Auto-create shop for new shop owner
        await create_shop_for_user(user_id, db)
        
        # Track analytics event
        await track_role_upgrade_event(user_id, 'SHOP_OWNER', 'subscription_payment', db)
        
        db.commit()
        logger.info(f"User {user_id} upgraded to SHOP_OWNER and subscription created")
        
    except Exception as e:
        logger.error(f"Error handling payment success: {str(e)}")
        db.rollback()


async def handle_payment_pending(transaction_data, db: Session):
    """Handle pending payment status"""
    try:
        custom_data = transaction_data.get('customData', {})
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in transaction customData")
            return
            
        logger.info(f"Payment pending for user {user_id}, maintaining current status")
        
        # Log the pending payment but don't change user status yet
        # Could implement notification system here to alert user
        
    except Exception as e:
        logger.error(f"Error handling payment pending: {str(e)}")


async def handle_payment_failed_tranzak(transaction_data, db: Session):
    """Handle failed payment for Tranzak"""
    try:
        custom_data = transaction_data.get('customData', {})
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in transaction customData")
            return
            
        logger.info(f"Payment failed for user {user_id}")
        
        # Find existing subscription if any
        subscription = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.status == 'active'
        ).first()
        
        if subscription:
            # Mark subscription as past_due
            subscription.status = 'past_due'
            
            # Downgrade user role
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.role = 'CASUAL_SELLER'
                
                # Deactivate shop
                shop = db.query(Shop).filter(Shop.owner_id == user_id).first()
                if shop:
                    shop.is_active = False
                    logger.info(f"Shop {shop.id} deactivated due to payment failure")
                
                # Track analytics event
                await track_role_upgrade_event(user_id, 'CASUAL_SELLER', 'payment_failed', db)
            
            db.commit()
            logger.info(f"User {user_id} downgraded due to payment failure")
        
    except Exception as e:
        logger.error(f"Error handling payment failure: {str(e)}")
        db.rollback()


async def handle_payment_cancelled(transaction_data, db: Session):
    """Handle cancelled payment"""
    try:
        custom_data = transaction_data.get('customData', {})
        user_id = custom_data.get('user_id')
        
        if not user_id:
            logger.error("No user_id in transaction customData")
            return
            
        logger.info(f"Payment cancelled for user {user_id}, no status change needed")
        
        # Payment was cancelled, no subscription was created
        # User remains in current role (typically CUSTOMER)
        
    except Exception as e:
        logger.error(f"Error handling payment cancellation: {str(e)}")


async def create_shop_for_user(user_id: str, db: Session):
    """Auto-create shop for new shop owner"""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User {user_id} not found for shop creation")
            return
            
        # Check if shop already exists
        existing_shop = db.query(Shop).filter(Shop.owner_id == user_id).first()
        if existing_shop:
            # Reactivate existing shop
            existing_shop.is_active = True
            logger.info(f"Reactivated existing shop {existing_shop.id} for user {user_id}")
            return
            
        # Generate shop name and slug
        shop_name = f"{user.first_name} {user.last_name}'s Shop".strip()
        if not shop_name or shop_name == "'s Shop":
            shop_name = f"Shop by {user.email.split('@')[0]}"
            
        shop_slug = shop_name.lower().replace(' ', '-').replace("'", "")
        
        # Create new shop
        new_shop = Shop(
            owner_id=user_id,
            name=shop_name,
            slug=shop_slug,
            description=f"Welcome to {shop_name}! Professional quality products and service.",
            address="",
            phone=user.phone or "",
            email=user.email,
            is_active=True,
            is_verified=False
        )
        
        db.add(new_shop)
        logger.info(f"Created new shop {shop_name} for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error creating shop for user {user_id}: {str(e)}")
        raise


async def track_role_upgrade_event(user_id: str, new_role: str, upgrade_method: str, db: Session):
    """Track role upgrade events for analytics"""
    try:
        from services.analytics_service import AnalyticsService
        
        analytics_service = AnalyticsService()
        
        await analytics_service.track_user_event(
            db=db,
            user_id=user_id,
            event_type='role_upgrade',
            metadata={
                'new_role': new_role,
                'upgrade_method': upgrade_method,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'source': 'tranzak_webhook'
            }
        )
        
        logger.info(f"Tracked role upgrade event for user {user_id}: {new_role} via {upgrade_method}")
        
    except Exception as e:
        logger.error(f"Error tracking role upgrade event: {str(e)}")
        # Don't fail the main process if analytics tracking fails