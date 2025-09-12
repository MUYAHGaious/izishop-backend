from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel
import logging
from datetime import datetime, timedelta

from database.connection import get_db
from models.user import User
from models.subscription import Subscription
from routers.auth import get_current_user

router = APIRouter(prefix="/api/subscription", tags=["subscription-management"])
logger = logging.getLogger(__name__)

class SubscriptionCancellationRequest(BaseModel):
    reason: str
    user_id: int

class RoleDowngradeRequest(BaseModel):
    new_role: str
    user_id: int
    current_role: str

class SubscriptionResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    request: SubscriptionCancellationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cancel a user's subscription and downgrade to free user
    """
    try:
        # Verify the user is cancelling their own subscription
        if current_user.id != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel your own subscription"
            )

        # Get the user's active subscription
        subscription = db.query(Subscription).filter(
            Subscription.user_id == request.user_id,
            Subscription.status == "active"
        ).first()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription found"
            )

        # Update subscription status
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.utcnow()
        subscription.cancellation_reason = request.reason
        subscription.ends_at = datetime.utcnow()  # Immediate cancellation

        # Downgrade user role to FREE
        user = db.query(User).filter(User.id == request.user_id).first()
        if user:
            user.role = "FREE"
            
            # Archive user's products (soft delete)
            from models.product import Product
            products = db.query(Product).filter(Product.seller_id == user.id).all()
            for product in products:
                product.is_active = False
                product.archived_at = datetime.utcnow()
                product.archive_reason = "Subscription cancelled"

            # Archive shop profile if exists
            from models.shop import Shop
            shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if shop:
                shop.is_active = False
                shop.archived_at = datetime.utcnow()
                shop.archive_reason = "Subscription cancelled"

        db.commit()

        logger.info(f"Subscription cancelled for user {request.user_id}: {request.reason}")

        return SubscriptionResponse(
            success=True,
            message="Subscription cancelled successfully. Your account has been downgraded to free user.",
            data={
                "cancelled_at": subscription.cancelled_at.isoformat(),
                "new_role": "FREE",
                "data_impact": {
                    "products_archived": len(products) if 'products' in locals() else 0,
                    "shop_deactivated": shop is not None if 'shop' in locals() else False
                }
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling subscription: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription"
        )

@router.post("/downgrade", response_model=SubscriptionResponse)
async def downgrade_role(
    request: RoleDowngradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Downgrade user role and adjust subscription accordingly
    """
    try:
        # Verify the user is downgrading their own role
        if current_user.id != request.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only downgrade your own role"
            )

        # Validate new role
        valid_roles = ["CUSTOMER", "DELIVERY_AGENT", "CASUAL_SELLER", "FREE"]
        if request.new_role not in valid_roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
            )

        # Get the user
        user = db.query(User).filter(User.id == request.user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        # Get active subscription
        subscription = db.query(Subscription).filter(
            Subscription.user_id == request.user_id,
            Subscription.status == "active"
        ).first()

        data_impact = {}
        old_role = user.role

        # Handle role-specific downgrade logic
        if request.new_role == "FREE":
            # Cancel subscription and archive data
            if subscription:
                subscription.status = "cancelled"
                subscription.cancelled_at = datetime.utcnow()
                subscription.cancellation_reason = f"Downgraded from {old_role} to FREE"
                subscription.ends_at = datetime.utcnow()

            # Archive all products
            from ..models.product import Product
            products = db.query(Product).filter(Product.seller_id == user.id).all()
            for product in products:
                product.is_active = False
                product.archived_at = datetime.utcnow()
                product.archive_reason = f"Role downgraded from {old_role} to FREE"
            data_impact["products_archived"] = len(products)

            # Archive shop profile
            from ..models.shop import Shop
            shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if shop:
                shop.is_active = False
                shop.archived_at = datetime.utcnow()
                shop.archive_reason = f"Role downgraded from {old_role} to FREE"
            data_impact["shop_deactivated"] = shop is not None

        elif request.new_role == "CASUAL_SELLER":
            # Keep subscription but limit products to 10
            from models.product import Product
            products = db.query(Product).filter(
                Product.seller_id == user.id,
                Product.is_active == True
            ).all()
            
            if len(products) > 10:
                # Archive excess products (keep the 10 most recent)
                products_to_archive = sorted(products, key=lambda x: x.created_at)[:-10]
                for product in products_to_archive:
                    product.is_active = False
                    product.archived_at = datetime.utcnow()
                    product.archive_reason = f"Role downgraded to CASUAL_SELLER - product limit exceeded"
                data_impact["products_archived"] = len(products_to_archive)
            else:
                data_impact["products_archived"] = 0

            # Update subscription plan
            if subscription:
                subscription.plan = "casual_seller"
                subscription.amount = 0  # Free plan

        elif request.new_role == "DELIVERY_AGENT":
            # Archive selling-related data
            from models.product import Product
            products = db.query(Product).filter(Product.seller_id == user.id).all()
            for product in products:
                product.is_active = False
                product.archived_at = datetime.utcnow()
                product.archive_reason = f"Role downgraded from {old_role} to DELIVERY_AGENT"
            data_impact["products_archived"] = len(products)

            # Archive shop profile
            from models.shop import Shop
            shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if shop:
                shop.is_active = False
                shop.archived_at = datetime.utcnow()
                shop.archive_reason = f"Role downgraded from {old_role} to DELIVERY_AGENT"
            data_impact["shop_deactivated"] = shop is not None

            # Cancel subscription
            if subscription:
                subscription.status = "cancelled"
                subscription.cancelled_at = datetime.utcnow()
                subscription.cancellation_reason = f"Downgraded from {old_role} to DELIVERY_AGENT"
                subscription.ends_at = datetime.utcnow()

        elif request.new_role == "CUSTOMER":
            # Archive all selling data
            from models.product import Product
            products = db.query(Product).filter(Product.seller_id == user.id).all()
            for product in products:
                product.is_active = False
                product.archived_at = datetime.utcnow()
                product.archive_reason = f"Role downgraded from {old_role} to CUSTOMER"
            data_impact["products_archived"] = len(products)

            # Archive shop profile
            from models.shop import Shop
            shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if shop:
                shop.is_active = False
                shop.archived_at = datetime.utcnow()
                shop.archive_reason = f"Role downgraded from {old_role} to CUSTOMER"
            data_impact["shop_deactivated"] = shop is not None

            # Cancel subscription
            if subscription:
                subscription.status = "cancelled"
                subscription.cancelled_at = datetime.utcnow()
                subscription.cancellation_reason = f"Downgraded from {old_role} to CUSTOMER"
                subscription.ends_at = datetime.utcnow()

        # Update user role
        user.role = request.new_role

        db.commit()

        logger.info(f"User {request.user_id} downgraded from {old_role} to {request.new_role}")

        return SubscriptionResponse(
            success=True,
            message=f"Successfully downgraded to {request.new_role}",
            data={
                "old_role": old_role,
                "new_role": request.new_role,
                "downgraded_at": datetime.utcnow().isoformat(),
                "data_impact": data_impact
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downgrading role: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to downgrade role"
        )

@router.get("/status/{user_id}")
async def get_subscription_status(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user's subscription status and role information
    """
    try:
        # Verify the user is checking their own status
        if current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only check your own subscription status"
            )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        subscription = db.query(Subscription).filter(
            Subscription.user_id == user_id,
            Subscription.status == "active"
        ).first()

        return {
            "success": True,
            "data": {
                "user_id": user.id,
                "role": user.role,
                "subscription": {
                    "status": subscription.status if subscription else "none",
                    "plan": subscription.plan if subscription else None,
                    "amount": subscription.amount if subscription else 0,
                    "next_billing": subscription.next_billing_date.isoformat() if subscription and subscription.next_billing_date else None
                } if subscription else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subscription status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get subscription status"
        )
