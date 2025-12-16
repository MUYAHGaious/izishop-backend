"""
Payment Audit Log Model

Complete audit trail for all payment transactions with security and compliance
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Numeric, Text, Boolean, JSON, Integer
from sqlalchemy.dialects.postgresql import JSONB
from database.base import Base


class PaymentLog(Base):
    """
    Comprehensive payment audit log
    
    Tracks every payment attempt, success, failure with complete details
    for security, compliance, and troubleshooting
    """
    __tablename__ = "payment_logs"

    # Primary identification
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    
    # Transaction identification
    transaction_id = Column(String(100), unique=True, nullable=False, index=True)
    order_id = Column(String, nullable=False, index=True)
    
    # User & customer information
    customer_id = Column(String, nullable=False, index=True)
    customer_email = Column(String(255), nullable=True)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(50), nullable=True)
    
    # Payment details
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="XAF", nullable=False)
    payment_method = Column(String(50), nullable=False)  # mtn_momo, orange_money
    payment_provider = Column(String(50), default="mesomb", nullable=False)
    
    # Transaction status
    status = Column(String(50), nullable=False, index=True)  # initiated, processing, completed, failed, cancelled
    previous_status = Column(String(50), nullable=True)
    
    # Request & Response data (sanitized)
    request_data = Column(JSON, nullable=True)  # Sanitized request payload
    response_data = Column(JSON, nullable=True)  # Provider response
    error_message = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)
    
    # Security & audit information
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    user_agent = Column(String(500), nullable=True)
    session_id = Column(String(100), nullable=True)
    
    # Timing information
    initiated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)  # Milliseconds
    
    # Provider-specific details
    provider_transaction_id = Column(String(255), nullable=True, index=True)
    provider_status_code = Column(String(50), nullable=True)
    provider_message = Column(Text, nullable=True)
    provider_metadata = Column(JSON, nullable=True)
    
    # Retry & failure tracking
    attempt_number = Column(Integer, default=1, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    is_retryable = Column(Boolean, default=False, nullable=False)
    retry_after = Column(DateTime, nullable=True)
    
    # Fraud & risk assessment
    risk_score = Column(Numeric(5, 2), nullable=True)  # 0-100
    fraud_check_passed = Column(Boolean, default=True, nullable=False)
    fraud_flags = Column(JSON, nullable=True)
    
    # Reconciliation
    reconciled = Column(Boolean, default=False, nullable=False, index=True)
    reconciled_at = Column(DateTime, nullable=True)
    reconciliation_status = Column(String(50), nullable=True)
    
    # Additional metadata
    metadata = Column(JSON, nullable=True)  # Any extra data
    notes = Column(Text, nullable=True)  # Admin notes
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<PaymentLog {self.transaction_id} - {self.status} - {self.amount} {self.currency}>"


class PaymentAttempt(Base):
    """
    Individual payment attempt tracking
    
    For scenarios with retries, tracks each attempt separately
    """
    __tablename__ = "payment_attempts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    payment_log_id = Column(String, nullable=False, index=True)  # References PaymentLog
    transaction_id = Column(String(100), nullable=False, index=True)
    
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    
    # Request details for this attempt
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    
    error_message = Column(Text, nullable=True)
    error_code = Column(String(100), nullable=True)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Network details
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<PaymentAttempt {self.transaction_id} - Attempt {self.attempt_number} - {self.status}>"


class PaymentWebhook(Base):
    """
    Webhook notifications from payment provider
    
    Tracks all webhooks received from MeSomb for audit and debugging
    """
    __tablename__ = "payment_webhooks"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    transaction_id = Column(String(100), nullable=True, index=True)
    
    # Webhook details
    webhook_type = Column(String(100), nullable=False)  # payment.success, payment.failed, etc.
    provider = Column(String(50), default="mesomb", nullable=False)
    
    # Payload
    raw_payload = Column(JSON, nullable=False)  # Complete webhook data
    parsed_status = Column(String(50), nullable=True)
    
    # Security
    signature = Column(String(500), nullable=True)
    signature_valid = Column(Boolean, nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    # Processing
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    processing_error = Column(Text, nullable=True)
    
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f"<PaymentWebhook {self.webhook_type} - {self.transaction_id}>"
