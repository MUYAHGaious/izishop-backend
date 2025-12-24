"""
MeSomb Payment Service

This service handles all MeSomb payment operations including:
- Payment collection from customers
- Transaction status checking
- Payment verification
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

try:
    from pymesomb.operations import PaymentOperation
    from pymesomb.utils import RandomGenerator
    PYMESOMB_AVAILABLE = True
except ImportError:
    PYMESOMB_AVAILABLE = False
    logging.warning("pymesomb not installed. Payment processing will be simulated in development mode.")

from core.mesomb_config import mesomb_settings

logger = logging.getLogger(__name__)


class MeSombService:
    """Service for handling MeSomb payment operations"""

    def __init__(self):
        """Initialize MeSomb payment operation client"""
        self.is_configured = mesomb_settings.is_configured()
        self.test_mode = mesomb_settings.MESOMB_TEST_MODE

        if PYMESOMB_AVAILABLE and self.is_configured:
            try:
                self.operation = PaymentOperation(
                    mesomb_settings.MESOMB_APPLICATION_KEY,
                    mesomb_settings.MESOMB_ACCESS_KEY,
                    mesomb_settings.MESOMB_SECRET_KEY
                )
                logger.info("✅ MeSomb service initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize MeSomb operation: {str(e)}")
                self.operation = None
        else:
            self.operation = None
            if not self.is_configured:
                logger.warning("⚠️ MeSomb not configured. Check environment variables.")

    async def collect_payment(
        self,
        amount: float,
        service: str,
        payer_phone: str,
        transaction_id: str,
        customer_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Collect payment from customer's mobile money account

        Args:
            amount: Payment amount in XAF
            service: Payment service ('MTN' or 'Orange')
            payer_phone: Customer's phone number
            transaction_id: Unique transaction identifier
            customer_data: Optional customer information

        Returns:
            Dictionary with payment result
        """
        try:
            logger.info(f"💳 Initiating MeSomb payment collection:")
            logger.info(f"   Amount: {amount} XAF")
            logger.info(f"   Service: {service}")
            logger.info(f"   Payer: {payer_phone}")
            logger.info(f"   Transaction ID: {transaction_id}")

            # Validate minimum amount (MeSomb requires minimum 100 XAF)
            MIN_AMOUNT = 100
            if amount < MIN_AMOUNT:
                logger.error(f"❌ Amount {amount} XAF is below minimum {MIN_AMOUNT} XAF")
                return {
                    'success': False,
                    'transaction_id': transaction_id,
                    'status': 'failed',
                    'error': f'Minimum payment amount is {MIN_AMOUNT} XAF',
                    'message': f'Payment amount must be at least {MIN_AMOUNT} XAF'
                }

            # Development/Test Mode - Simulate payment
            if self.test_mode or not PYMESOMB_AVAILABLE or not self.operation:
                logger.warning("🧪 TEST MODE: Simulating MeSomb payment")
                return self._simulate_payment_success(transaction_id, amount, service)

            # Production Mode - Real MeSomb payment
            # Generate nonce for security
            nonce = RandomGenerator.nonce()

            # Make the payment collection request using keyword arguments
            logger.info("📡 Sending payment request to MeSomb...")
            logger.info(f"   Using nonce: {nonce}")

            response = self.operation.make_collect(
                amount=int(amount),  # MeSomb expects integer amount in XAF
                service=service,  # MTN or Orange
                payer=payer_phone,  # Customer phone number
                nonce=nonce,  # Unique request identifier
                country='CM',  # Cameroon
                currency='XAF',  # Central African Franc
                fees=True,  # Fees paid by customer
                mode='synchronous',  # Wait for response
                conversion=False,  # No currency conversion
                customer=customer_data,  # Customer information
                trx_id=transaction_id  # Our transaction ID
            )

            # Log detailed response information
            logger.info(f"📊 MeSomb API Response Details:")
            logger.info(f"   Response Object: {response}")
            logger.info(f"   Response Type: {type(response)}")

            # Try to log all response attributes
            try:
                if hasattr(response, '__dict__'):
                    logger.info(f"   Response Attributes: {response.__dict__}")
            except Exception as e:
                logger.warning(f"   Could not log response attributes: {e}")

            # Check operation and transaction success
            operation_success = response.is_operation_success()
            transaction_success = response.is_transaction_success()

            logger.info(f"📊 MeSomb Status Checks:")
            logger.info(f"   Operation Success: {operation_success}")
            logger.info(f"   Transaction Success: {transaction_success}")

            # Try to get more details from response
            try:
                if hasattr(response, 'message'):
                    logger.info(f"   Response Message: {response.message}")
                if hasattr(response, 'success'):
                    logger.info(f"   Response Success: {response.success}")
                if hasattr(response, 'status'):
                    logger.info(f"   Response Status: {response.status}")
                if hasattr(response, 'data'):
                    logger.info(f"   Response Data: {response.data}")
            except Exception as e:
                logger.warning(f"   Could not extract additional response details: {e}")

            if operation_success and transaction_success:
                logger.info("✅ Payment collected successfully")
                return {
                    'success': True,
                    'transaction_id': transaction_id,
                    'status': 'completed',
                    'message': 'Payment collected successfully',
                    'amount': amount,
                    'service': service,
                    'mesomb_response': str(response)
                }
            else:
                # Check if payment was canceled/declined
                logger.warning("⚠️ Payment not successful - checking status")

                # Try to get status from response
                status = 'pending'  # Default
                message = 'Payment is being processed'

                try:
                    if hasattr(response, 'status'):
                        response_status = str(response.status).lower()
                        logger.info(f"   Response status: {response_status}")

                        if 'cancel' in response_status or 'decline' in response_status or 'refused' in response_status:
                            status = 'canceled'
                            message = 'Payment was canceled or declined by user'
                            logger.warning(f"❌ Payment canceled: {response_status}")

                    # Check message for cancellation keywords
                    if hasattr(response, 'message'):
                        response_message = str(response.message).lower()
                        if any(keyword in response_message for keyword in ['cancel', 'decline', 'refuse', 'reject', 'timeout']):
                            status = 'canceled'
                            message = 'Payment was canceled or timed out'
                            logger.warning(f"❌ Payment canceled from message: {response_message}")
                except Exception as e:
                    logger.warning(f"Could not extract detailed status: {e}")

                logger.warning(f"⚠️ Payment status: {status} - {message}")
                return {
                    'success': False,
                    'transaction_id': transaction_id,
                    'status': status,
                    'message': message,
                    'mesomb_response': str(response)
                }

        except Exception as e:
            logger.error(f"❌ MeSomb payment collection failed: {str(e)}")
            logger.error(f"   Exception Type: {type(e)}")
            logger.error(f"   Exception Details: {e}")

            # Check for authentication errors
            error_msg = str(e).lower()

            # Detect user cancellation/timeout from exception
            if any(keyword in error_msg for keyword in ['timeout', 'cancelled', 'canceled', 'declined', 'refused', 'reject']):
                logger.warning(f"❌ Payment canceled/timeout: {error_msg}")
                return {
                    'success': False,
                    'transaction_id': transaction_id,
                    'status': 'canceled',
                    'error': str(e),
                    'message': 'Payment was canceled or timed out'
                }

            if 'auth' in error_msg or 'credential' in error_msg or 'key' in error_msg or 'unauthorized' in error_msg:
                logger.error("🔑 AUTHENTICATION ERROR: Check your MeSomb API keys!")
                logger.error(f"   Application Key: {mesomb_settings.MESOMB_APPLICATION_KEY[:10]}...")
                logger.error(f"   Access Key: {mesomb_settings.MESOMB_ACCESS_KEY[:10]}...")

            return {
                'success': False,
                'transaction_id': transaction_id,
                'status': 'failed',
                'error': str(e),
                'message': f'Payment failed: {str(e)}'
            }

    async def check_transaction_status(
        self,
        transaction_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Check the status of one or more transactions

        Args:
            transaction_ids: List of transaction IDs to check

        Returns:
            Dictionary with transaction status information
        """
        try:
            logger.info(f"🔍 Checking transaction status for: {transaction_ids}")

            # Development/Test Mode
            if self.test_mode or not PYMESOMB_AVAILABLE or not self.operation:
                logger.warning("🧪 TEST MODE: Simulating transaction status check")
                return {
                    'success': True,
                    'transactions': [
                        {
                            'id': tid,
                            'status': 'completed',
                            'message': 'Test transaction'
                        } for tid in transaction_ids
                    ]
                }

            # Production Mode
            response = self.operation.get_transactions(transaction_ids)

            logger.info("✅ Transaction status retrieved successfully")
            return {
                'success': True,
                'transactions': response
            }

        except Exception as e:
            logger.error(f"❌ Failed to check transaction status: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Status check failed: {str(e)}'
            }

    async def get_application_status(self) -> Dict[str, Any]:
        """
        Get MeSomb application status

        Returns:
            Dictionary with application status
        """
        try:
            logger.info("🔍 Checking MeSomb application status")

            # Check configuration
            if not self.is_configured:
                return {
                    'success': False,
                    'configured': False,
                    'message': 'MeSomb credentials not configured'
                }

            # Development/Test Mode
            if self.test_mode or not PYMESOMB_AVAILABLE or not self.operation:
                return {
                    'success': True,
                    'configured': True,
                    'test_mode': True,
                    'message': 'MeSomb in test mode'
                }

            # Production Mode
            response = self.operation.get_status()

            logger.info("✅ Application status retrieved")
            return {
                'success': True,
                'configured': True,
                'test_mode': False,
                'status': response
            }

        except Exception as e:
            logger.error(f"❌ Failed to get application status: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f'Status check failed: {str(e)}'
            }

    def _simulate_payment_success(
        self,
        transaction_id: str,
        amount: float,
        service: str
    ) -> Dict[str, Any]:
        """Simulate successful payment for testing"""
        return {
            'success': True,
            'transaction_id': transaction_id,
            'status': 'completed',
            'message': '✅ TEST MODE: Payment simulated successfully',
            'amount': amount,
            'service': service,
            'test_mode': True
        }


# Global service instance
mesomb_service = MeSombService()
