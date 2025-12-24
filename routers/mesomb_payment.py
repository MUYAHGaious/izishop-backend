"""
MeSomb Payment Router

API endpoints for handling MeSomb mobile money payments
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
import logging
import uuid

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from services.mesomb_service import mesomb_service, PYMESOMB_AVAILABLE
from models.order import Order, OrderStatus, PaymentStatus
from core.mesomb_config import mesomb_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Log module initialization
logger.info("=" * 80)
logger.info("MESOMB PAYMENT ROUTER MODULE INITIALIZED")
logger.info("=" * 80)

router = APIRouter(prefix="/mesomb", tags=["mesomb-payment"])


# Request/Response Schemas
class InitiatePaymentRequest(BaseModel):
    """Request schema for initiating a payment"""
    order_id: str = Field(..., description="Order ID to process payment for")
    payment_method: str = Field(..., description="Payment method: 'mtn_momo' or 'orange_money'")
    phone_number: str = Field(..., description="Customer's mobile money phone number")

    class Config:
        schema_extra = {
            "example": {
                "order_id": "550e8400-e29b-41d4-a716-446655440000",
                "payment_method": "mtn_momo",
                "phone_number": "237670000000"
            }
        }


class PaymentResponse(BaseModel):
    """Response schema for payment operations"""
    success: bool
    message: str
    order_id: str
    transaction_id: str
    status: str
    amount: Optional[float] = None


class TransactionStatusResponse(BaseModel):
    """Response schema for transaction status"""
    success: bool
    transaction_id: str
    status: str
    message: Optional[str] = None


class ApplicationStatusResponse(BaseModel):
    """Response schema for MeSomb application status"""
    success: bool
    configured: bool
    test_mode: bool
    message: str


@router.post("/initiate-payment", response_model=PaymentResponse)
async def initiate_payment(
    request: InitiatePaymentRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Initiate a payment collection from customer's mobile money account

    This endpoint:
    1. Validates the order belongs to the current user
    2. Checks payment hasn't already been completed
    3. Initiates payment collection via MeSomb
    4. Updates order status based on payment result

    Returns:
        PaymentResponse with transaction details
    """
    logger.info("=" * 80)
    logger.info("MESOMB PAYMENT ENDPOINT CALLED")
    logger.info("=" * 80)

    try:
        logger.info(f"[REQUEST DATA] order_id: {request.order_id}")
        logger.info(f"[REQUEST DATA] payment_method: {request.payment_method}")
        logger.info(f"[REQUEST DATA] phone_number: {request.phone_number}")
        logger.info(f"[USER DATA] user_id: {current_user.id}")
        logger.info(f"Payment initiation request from user {current_user.id}")
        logger.info(f"   Order ID: {request.order_id}")
        logger.info(f"   Payment Method: {request.payment_method}")

        # Step 1: Validate payment method
        if not mesomb_settings.validate_payment_method(request.payment_method):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid payment method. Supported: {list(mesomb_settings.SUPPORTED_SERVICES.keys())}"
            )

        # Step 2: Get and validate order
        order = db.query(Order).filter(
            Order.id == request.order_id,
            Order.customer_id == current_user.id
        ).first()

        if not order:
            logger.error(f"❌ Order {request.order_id} not found for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {request.order_id} not found or does not belong to you"
            )

        # Step 3: Check if order already paid
        if order.payment_status == PaymentStatus.PAID:
            logger.warning(f"⚠️ Order {request.order_id} already paid")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has already been paid"
            )

        # Step 4: Validate order has total_amount
        if order.total_amount is None:
            logger.error(f"❌ Order {request.order_id} has no total_amount")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order total amount is missing"
            )

        # Step 5: Generate unique transaction ID
        # Ensure order.id is a string before slicing
        order_id_str = str(order.id) if order.id else str(uuid.uuid4())
        transaction_id = f"IZISHOP_{order_id_str[:8]}_{uuid.uuid4().hex[:8].upper()}"
        logger.info(f"🔑 Generated transaction ID: {transaction_id}")

        # Step 6: Get MeSomb service name
        service_name = mesomb_settings.get_service_name(request.payment_method)
        if not service_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid payment method"
            )

        # Step 7: Prepare customer data
        customer_data = {
            'email': current_user.email or '',
            'name': f"{current_user.first_name or ''} {current_user.last_name or ''}".strip(),
            'phone': request.phone_number
        }

        # Step 8: Convert total_amount to float safely
        try:
            amount = float(order.total_amount)
            if amount <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Order amount must be greater than zero"
                )
        except (ValueError, TypeError) as e:
            logger.error(f"❌ Invalid order total_amount: {order.total_amount}, error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order amount: {order.total_amount}"
            )

        # Step 9: Initiate payment collection via MeSomb
        logger.info("📡 Calling MeSomb service to collect payment...")
        logger.info(f"   Amount: {amount} XAF")
        logger.info(f"   Service: {service_name}")
        logger.info(f"   Phone: {request.phone_number}")
        
        try:
            payment_result = await mesomb_service.collect_payment(
                amount=amount,
                service=service_name,
                payer_phone=request.phone_number,
                transaction_id=transaction_id,
                customer_data=customer_data
            )
            
            # Validate payment_result structure
            if not payment_result or not isinstance(payment_result, dict):
                logger.error(f"❌ Invalid payment result: {payment_result}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Invalid payment service response"
                )
            
            if 'success' not in payment_result:
                logger.error(f"❌ Payment result missing 'success' key: {payment_result}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Payment service returned invalid response"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Error calling MeSomb service: {str(e)}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initiate payment: {str(e)}"
            )

        # Step 10: Update order based on payment result
        if payment_result.get('success', False):
            logger.info("✅ Payment successful - updating order status")

            # Update order to PAID and CONFIRMED
            order.payment_status = PaymentStatus.PAID
            order.payment_method = request.payment_method
            order.status = OrderStatus.CONFIRMED
            order.payment_reference = transaction_id

            db.commit()
            db.refresh(order)

            logger.info(f"✅ Order {order.id} payment completed successfully")

            try:
                return PaymentResponse(
                    success=True,
                    message='Payment processed successfully',
                    order_id=str(order.id),
                    transaction_id=transaction_id,
                    status='completed',
                    amount=float(order.total_amount)
                )
            except Exception as e:
                logger.error(f"❌ Error creating PaymentResponse: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to create payment response: {str(e)}"
                )
        else:
            # Payment failed, pending, or canceled
            payment_status_str = payment_result.get('status', 'failed')
            message = payment_result.get('message', 'Payment processing')

            logger.warning(f"⚠️ Payment status: {payment_status_str} - {message}")

            # Check if payment was canceled by user
            if payment_status_str == 'canceled':
                logger.error(f"❌ Payment canceled by user")
                order.payment_status = PaymentStatus.FAILED
                order.payment_reference = transaction_id
                db.commit()

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Payment was canceled or declined. Please try again.'
                )

            # Check if payment is pending (being processed)
            if payment_status_str == 'pending':
                # Payment is being processed - keep order as PENDING
                logger.info("⏳ Payment pending - keeping order in PENDING state")
                order.payment_reference = transaction_id
                # Don't change payment_status - leave as PENDING
                db.commit()

                # Return 202 Accepted (not an error!)
                return PaymentResponse(
                    success=False,
                    message='Payment is being processed. Please check status shortly.',
                    order_id=str(order.id),
                    transaction_id=transaction_id,
                    status='pending',
                    amount=float(order.total_amount)
                )
            else:
                # Payment actually failed
                logger.error(f"❌ Payment failed: {message}")
                order.payment_status = PaymentStatus.FAILED
                order.payment_reference = transaction_id
                db.commit()

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=message
                )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"❌ Payment initiation error: {str(e)}")
        logger.error(f"❌ Full traceback:\n{error_traceback}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Payment processing failed: {str(e)}"
        )


@router.get("/check-status/{transaction_id}", response_model=TransactionStatusResponse)
async def check_payment_status(
    transaction_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check the status of a payment transaction

    Args:
        transaction_id: MeSomb transaction ID

    Returns:
        TransactionStatusResponse with current transaction status
    """
    try:
        logger.info(f"🔍 Checking payment status for transaction: {transaction_id}")

        # Verify transaction belongs to user's order
        order = db.query(Order).filter(
            Order.payment_reference == transaction_id,
            Order.customer_id == current_user.id
        ).first()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )

        # Check status with MeSomb
        result = await mesomb_service.check_transaction_status([transaction_id])

        if result['success']:
            logger.info("✅ Transaction status retrieved successfully")
            return TransactionStatusResponse(
                success=True,
                transaction_id=transaction_id,
                status=order.payment_status.value,
                message='Transaction status retrieved'
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Failed to retrieve transaction status"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Status check error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check transaction status: {str(e)}"
        )


@router.get("/application-status", response_model=ApplicationStatusResponse)
async def get_application_status(
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get MeSomb application configuration status

    This endpoint is useful for:
    - Checking if MeSomb is properly configured
    - Verifying test mode vs production mode
    - Health checks

    Returns:
        ApplicationStatusResponse with configuration details
    """
    try:
        logger.info("🔍 Checking MeSomb application status")

        status_result = await mesomb_service.get_application_status()

        return ApplicationStatusResponse(
            success=status_result['success'],
            configured=status_result.get('configured', False),
            test_mode=status_result.get('test_mode', True),
            message=status_result.get('message', 'Application status retrieved')
        )

    except Exception as e:
        logger.error(f"❌ Application status check error: {str(e)}")
        return ApplicationStatusResponse(
            success=False,
            configured=False,
            test_mode=True,
            message=f"Failed to check status: {str(e)}"
        )


@router.get("/test-credentials")
async def test_mesomb_credentials():
    """
    Test MeSomb API credentials without authentication

    This endpoint verifies if the MeSomb API keys are valid by:
    1. Checking if MeSomb is configured
    2. Testing the API connection
    3. Attempting to get application status from MeSomb

    Returns detailed information about credential validity
    """
    try:
        logger.info("=" * 80)
        logger.info("🔑 TESTING MESOMB CREDENTIALS")
        logger.info("=" * 80)

        # Step 1: Check configuration
        logger.info(f"📋 MeSomb Configuration:")
        logger.info(f"   Configured: {mesomb_service.is_configured}")
        logger.info(f"   Test Mode: {mesomb_service.test_mode}")
        logger.info(f"   Application Key: {mesomb_settings.MESOMB_APPLICATION_KEY[:10]}...{mesomb_settings.MESOMB_APPLICATION_KEY[-4:]}")
        logger.info(f"   Access Key: {mesomb_settings.MESOMB_ACCESS_KEY[:10]}...{mesomb_settings.MESOMB_ACCESS_KEY[-4:]}")

        if not mesomb_service.is_configured:
            return {
                "success": False,
                "configured": False,
                "test_mode": mesomb_service.test_mode,
                "message": "MeSomb credentials not configured in environment variables",
                "details": {
                    "application_key_set": bool(mesomb_settings.MESOMB_APPLICATION_KEY),
                    "access_key_set": bool(mesomb_settings.MESOMB_ACCESS_KEY),
                    "secret_key_set": bool(mesomb_settings.MESOMB_SECRET_KEY)
                }
            }

        # Step 2: Check if in test mode (simulation)
        if mesomb_service.test_mode:
            logger.info("⚠️ Running in TEST MODE (simulation)")
            return {
                "success": True,
                "configured": True,
                "test_mode": True,
                "message": "MeSomb is in test/simulation mode. Real API not being used.",
                "details": {
                    "pymesomb_available": PYMESOMB_AVAILABLE,
                    "operation_initialized": mesomb_service.operation is not None
                }
            }

        # Step 3: Check if pymesomb is available
        if not PYMESOMB_AVAILABLE:
            return {
                "success": False,
                "configured": True,
                "test_mode": False,
                "message": "pymesomb library not installed",
                "details": {
                    "error": "pymesomb package is not available"
                }
            }

        # Step 4: Test the actual API connection
        logger.info("📡 Testing MeSomb API connection...")
        try:
            status_result = await mesomb_service.get_application_status()

            if status_result.get('success'):
                logger.info("✅ MeSomb API credentials are VALID!")
                return {
                    "success": True,
                    "configured": True,
                    "test_mode": False,
                    "message": "✅ MeSomb API credentials are valid and working!",
                    "details": {
                        "api_response": status_result,
                        "connection_test": "successful"
                    }
                }
            else:
                logger.error("❌ MeSomb API returned error")
                return {
                    "success": False,
                    "configured": True,
                    "test_mode": False,
                    "message": "❌ MeSomb API returned error - credentials may be invalid",
                    "details": {
                        "error": status_result.get('message', 'Unknown error'),
                        "full_response": status_result
                    }
                }

        except Exception as api_error:
            logger.error(f"❌ MeSomb API call failed: {str(api_error)}")
            error_msg = str(api_error).lower()

            # Check for authentication errors
            if 'auth' in error_msg or 'credential' in error_msg or 'key' in error_msg or 'unauthorized' in error_msg or '401' in error_msg or '403' in error_msg:
                return {
                    "success": False,
                    "configured": True,
                    "test_mode": False,
                    "message": "❌ AUTHENTICATION FAILED - Your MeSomb API keys appear to be invalid!",
                    "details": {
                        "error": str(api_error),
                        "error_type": type(api_error).__name__,
                        "hint": "Please verify your Application Key, Access Key, and Secret Key in the MeSomb dashboard"
                    }
                }
            else:
                return {
                    "success": False,
                    "configured": True,
                    "test_mode": False,
                    "message": f"❌ API call failed: {str(api_error)}",
                    "details": {
                        "error": str(api_error),
                        "error_type": type(api_error).__name__
                    }
                }

    except Exception as e:
        logger.error(f"❌ Credential test failed: {str(e)}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "configured": False,
            "test_mode": False,
            "message": f"Test failed with error: {str(e)}",
            "details": {
                "error": str(e),
                "error_type": type(e).__name__
            }
        }
