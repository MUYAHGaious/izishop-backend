"""
Tranzak webhooks and subscription management for IziShopin
"""
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.shop import Shop
from models.subscription import Subscription
from models.order import PaymentStatus
from services.payment_distribution import PaymentDistributionService
import httpx
import json
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel

class PaymentRequest(BaseModel):
    paymentMethod: str
    phoneNumber: Optional[str] = None
    operator: Optional[str] = None
    cardDetails: Optional[Dict[str, str]] = None

# Configure Tranzak
TRANZAK_BASE_URL = os.getenv('TRANZAK_BASE_URL', 'https://sandbox.dsapi.tranzak.me')  # Default to sandbox
TRANZAK_APP_ID = os.getenv('TRANZAK_API_KEY', 'ap6kbj7jhunqq4')  # Use TRANZAK_API_KEY for app ID
TRANZAK_APP_KEY = os.getenv('TRANZAK_API_SECRET', 'SAND_6BD375A02D9447318E5798F8C8AF1914')  # Use TRANZAK_API_SECRET for app key
TRANZAK_WEBHOOK_SECRET = os.getenv('TRANZAK_WEBHOOK_SECRET', 'dev_webhook_secret')

router = APIRouter(prefix="/api/tranzak", tags=["tranzak"])
logger = logging.getLogger(__name__)

async def get_tranzak_token(scope: str = "collections") -> str:
    """Get authentication token from Tranzak API"""
    # Check if Tranzak credentials are configured
    if not TRANZAK_APP_ID or not TRANZAK_APP_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment service is not configured. Please contact support for manual upgrade."
        )
    
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
                logger.error(f"Tranzak auth failed: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to authenticate with Tranzak"
                )
            
            response_data = response.json()
            if not response_data.get("success", False):
                logger.error(f"Tranzak auth error: {response_data}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tranzak authentication failed - invalid credentials"
                )
            
            token_response = response.json()
            
            # Check if authentication was successful according to official API
            if not token_response.get('success', False):
                error_msg = token_response.get('errorMsg', 'Authentication failed')
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tranzak authentication error: {error_msg}"
                )
            
            # Handle different possible response structures
            if "data" in token_response and "token" in token_response["data"]:
                return token_response["data"]["token"]
            elif "token" in token_response:
                return token_response["token"]
            else:
                logger.error(f"No token found in response: {token_response}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Authentication successful but no token returned"
                )
    except Exception as e:
        logger.error(f"Error getting Tranzak token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Payment service authentication failed"
        )

async def simulate_development_subscription(user: User, db: Session):
    """Simulate a successful subscription in development mode"""
    try:
        from datetime import datetime, timedelta
        from models.subscription import Subscription
        from models.user import User as UserModel
        
        # Create subscription record
        subscription = Subscription(
            user_id=user.id,
            plan_type="shop_owner",
            status="active",
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30),
            monthly_fee=29.99,
            trial_ends_at=datetime.utcnow() + timedelta(days=7),
            tranzak_request_id=f"dev_sub_{user.id}_{int(datetime.utcnow().timestamp())}"
        )
        
        db.add(subscription)
        
        # Update user role to SHOP_OWNER
        user_model = db.query(UserModel).filter(UserModel.id == user.id).first()
        if user_model:
            user_model.role = "SHOP_OWNER"
            user_model.subscription_status = "active"
            user_model.role_upgraded_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"DEVELOPMENT: Successfully created subscription for user {user.id}")
        
        return {
            "success": True,
            "message": "Subscription activated successfully! (Development Mode)",
            "subscription_id": subscription.id,
            "payment_url": None,  # No payment URL needed in dev mode
            "user_role": "SHOP_OWNER",
            "trial_ends_at": subscription.trial_ends_at.isoformat(),
            "next_billing_date": subscription.current_period_end.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in development subscription simulation: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create development subscription"
        )

@router.post("/create-shop-subscription")
async def create_shop_subscription(
    payment_request: PaymentRequest,
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
            # Check if the user's role is already shop_owner
            if current_user.role == 'shop_owner':
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You are already a shop owner with an active subscription. No need to upgrade again!"
                )
            else:
                # User has a subscription but not the role - this is a data inconsistency
                # This can happen if:
                # 1. Payment succeeded but role upgrade failed
                # 2. Manual database changes
                # 3. Previous upgrade attempt was interrupted
                logger.warning(
                    f"Data inconsistency detected: User {current_user.id} has active subscription "
                    f"(ID: {existing_sub.id}, status: {existing_sub.status}) but role is {current_user.role}, not shop_owner. "
                    f"Cancelling old subscription to allow fresh upgrade."
                )
                existing_sub.status = 'cancelled'
                existing_sub.cancelled_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"Successfully cancelled stale subscription {existing_sub.id} for user {current_user.id}")
        
        # DEVELOPMENT MODE: Check if we're in development
        is_development = os.getenv('ENVIRONMENT', 'development').lower() in ['development', 'dev', 'local']
        
        if is_development:
            logger.info(f"DEVELOPMENT MODE: Simulating successful subscription for user {current_user.id}")
            return await simulate_development_subscription(current_user, db)
        
        # Get Tranzak authentication token
        token = await get_tranzak_token()
        
        # Create payment request
        base_url = request.url.scheme + "://" + request.url.netloc
        
        # Generate unique transaction reference to prevent duplicates
        import uuid
        transaction_ref = f"shop_sub_{current_user.id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Extract payment method and details from request
        payment_method = payment_request.paymentMethod
        
        # Base payment data
        payment_data = {
            "amount": 29.99,  # $29.99 monthly fee
            "currencyCode": "USD",
            "description": "IziShopin Shop Owner Subscription - Monthly Plan",
            "mchTransactionRef": transaction_ref,  # Unique reference for duplicate prevention
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
        
        # Determine endpoint and modify payload based on payment method
        if payment_method in ['mtn_money', 'orange_money']:
            # Use mobile wallet charge endpoint
            endpoint = f"{TRANZAK_BASE_URL}/xp021/v1/request/create-mobile-wallet-charge"
            payment_data.update({
                "mobileWalletNumber": payment_request.phoneNumber or '',
                "walletProvider": "MTN" if payment_method == 'mtn_money' else "ORANGE"
            })
        else:
            # Use web redirect payment endpoint for cards and other methods
            endpoint = f"{TRANZAK_BASE_URL}/xp021/v1/request/create"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                endpoint,
                json=payment_data,
                headers=headers
            )
            
            if response.status_code != 200:
                logger.error(f"Tranzak API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to create payment request"
                )
            
            payment_response = response.json()
            
            # Check if request was successful according to official API
            if not payment_response.get('success', False):
                error_msg = payment_response.get('errorMsg', 'Unknown error')
                logger.error(f"Tranzak API returned error: {error_msg}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Payment request failed: {error_msg}"
                )
            
            data = payment_response.get('data', {})
            logger.info(f"Created Tranzak payment request {data.get('requestId')} for user {current_user.id}")
            
            return {
                'payment_url': data.get('paymentAuthUrl'),
                'request_id': data.get('requestId'),
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
        
        # Handle different event types based on official Tranzak documentation
        if event_type == 'REQUEST.COMPLETED':
            # Check transaction status within the completed request
            request_status = transaction_data.get('requestStatus')
            if request_status == 'SUCCESSFUL':
                # Check if this is an order payment or subscription payment
                custom_data = transaction_data.get('customData', {})
                order_id = custom_data.get('orderId')
                
                if order_id:
                    # This is an order payment
                    await handle_order_payment_successful(transaction_data, db)
                else:
                    # This is a subscription payment
                    await handle_payment_successful(transaction_data, db)
            elif request_status == 'FAILED':
                await handle_payment_failed_tranzak(transaction_data, db)
            elif request_status == 'CANCELLED':
                await handle_payment_cancelled(transaction_data, db)
            else:
                logger.info(f"Unknown request status in completed event: {request_status}")
                
        # Legacy support for old event types (keep for backward compatibility)
        elif event_type == 'PAYMENT_SUCCESSFUL' or transaction_data.get('status') == 'SUCCESSFUL':
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


async def handle_order_payment_successful(transaction_data, db: Session):
    """Handle successful order payment completion"""
    try:
        custom_data = transaction_data.get('customData', {})
        order_id = custom_data.get('orderId')
        customer_id = custom_data.get('customerId')
        amount = transaction_data.get('amount', 0)
        
        if not order_id:
            logger.error("No orderId in transaction customData")
            return
            
        logger.info(f"Order payment successful for order {order_id}")
        
        # Initialize payment distribution service
        payment_service = PaymentDistributionService(db)
        
        # Check if this is a multi-vendor order
        master_order = db.query(Order).filter(Order.id == order_id).first()
        
        if master_order and master_order.shop_id is None:
            # This is a master order (multi-vendor)
            logger.info(f"Processing multi-vendor payment for master order {order_id}")
            
            # Distribute payment to vendors
            distribution_result = await payment_service.distribute_multi_vendor_payment(
                master_order_id=order_id,
                payment_reference=transaction_data.get('requestId', ''),
                total_payment_amount=Decimal(str(amount))
            )
            
            logger.info(f"Payment distribution completed: {distribution_result}")
            
        else:
            # This is a single-vendor order
            logger.info(f"Processing single-vendor payment for order {order_id}")
            
            # Update order payment status
            order = db.query(Order).filter(Order.id == order_id).first()
            if order:
                order.payment_status = PaymentStatus.PAID
                order.updated_at = datetime.now(timezone.utc)
                
                # Send notification to vendor
                shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
                if shop:
                    vendor = db.query(User).filter(User.id == shop.owner_id).first()
                    if vendor:
                        from models.notification import Notification, NotificationType, NotificationPriority
                        
                        notification = Notification(
                            user_id=vendor.id,
                            type=NotificationType.PAYMENT,
                            title="💰 Payment Received!",
                            message=f"""Great news! You've received a payment for your order.

💳 PAYMENT DETAILS:
• Order ID: {order.id}
• Amount: ${order.total_amount}
• Payment Reference: {transaction_data.get('requestId', 'N/A')}

🚀 NEXT STEPS:
1. Review order details in your dashboard
2. Prepare items for shipping
3. Update order status when ready to ship

Need help? Contact our support team anytime!

IziShopin Team 🚀""",
                            related_id=order.id,
                            related_type="payment_received",
                            priority=NotificationPriority.HIGH,
                            action_url=f"/shop-owner-dashboard/orders/{order.id}",
                            action_label="View Order",
                            icon="CreditCard"
                        )
                        
                        db.add(notification)
                        logger.info(f"Created payment notification for vendor {vendor.email}")
        
        db.commit()
        logger.info(f"Order payment processing completed for order {order_id}")
        
    except Exception as e:
        logger.error(f"Error handling order payment success: {str(e)}")
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
