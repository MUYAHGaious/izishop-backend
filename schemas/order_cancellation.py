from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime

class CancellationReason(str, Enum):
    """Order cancellation reasons based on industry standards"""
    CUSTOMER_REQUEST = "customer_request"
    PAYMENT_FAILED = "payment_failed"
    INVENTORY_UNAVAILABLE = "inventory_unavailable"
    SHIPPING_ISSUES = "shipping_issues"
    DUPLICATE_ORDER = "duplicate_order"
    PRICING_ERROR = "pricing_error"
    CUSTOMER_CHANGED_MIND = "customer_changed_mind"
    WRONG_ITEM_ORDERED = "wrong_item_ordered"
    DELIVERY_ISSUES = "delivery_issues"
    OTHER = "other"

class CancellationRequest(BaseModel):
    """Request schema for order cancellation"""
    reason: CancellationReason
    description: Optional[str] = Field(None, max_length=500, description="Additional details about cancellation")
    refund_requested: bool = Field(True, description="Whether customer wants refund")
    restock_items: bool = Field(True, description="Whether to return items to inventory")

class CancellationResponse(BaseModel):
    """Response schema for order cancellation"""
    success: bool
    message: str
    order_id: str
    cancellation_id: Optional[str] = None
    refund_amount: Optional[float] = None
    refund_status: Optional[str] = None
    estimated_refund_time: Optional[str] = None
    cancelled_at: datetime
    items_restocked: bool = False

class CancellationPolicy(BaseModel):
    """Cancellation policy information"""
    can_cancel: bool
    reason: str
    time_limit_hours: Optional[int] = None
    refund_percentage: float = 100.0
    cancellation_fee: float = 0.0

class OrderCancellationHistory(BaseModel):
    """Order cancellation history record"""
    id: str
    order_id: str
    cancellation_reason: CancellationReason
    description: Optional[str]
    cancelled_by: str  # user_id
    cancelled_at: datetime
    refund_amount: Optional[float]
    refund_status: str
    items_restocked: bool