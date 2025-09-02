"""
Transaction Fee Management for Casual Marketplace
Handles 5% transaction fees when casual items are sold
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func, extract
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.casual_listing import CasualListing
from models.transaction_fee import TransactionFee
from decimal import Decimal
import uuid

router = APIRouter(prefix="/api/transaction-fees", tags=["transaction-fees"])
logger = logging.getLogger(__name__)

# Constants
CASUAL_SELLER_FEE_RATE = Decimal('0.05')  # 5% transaction fee

@router.post("/record-sale/{listing_id}")
async def record_casual_sale(
    listing_id: str,
    buyer_id: str,
    final_sale_price: float,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Record a casual listing sale and calculate transaction fee"""
    try:
        # Get the listing
        listing = db.query(CasualListing).filter(
            CasualListing.id == listing_id
        ).first()
        
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Listing not found"
            )
        
        # Verify the current user is the seller
        if listing.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the seller can record this sale"
            )
        
        # Check if listing is still active
        if not listing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This listing is no longer active"
            )
        
        sale_price = Decimal(str(final_sale_price))
        fee_amount = sale_price * CASUAL_SELLER_FEE_RATE
        seller_earnings = sale_price - fee_amount
        
        # Create transaction fee record
        transaction_fee = TransactionFee(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            listing_id=listing_id,
            buyer_id=buyer_id,
            sale_amount=sale_price,
            fee_rate=CASUAL_SELLER_FEE_RATE,
            fee_amount=fee_amount,
            seller_earnings=seller_earnings,
            fee_status='pending',  # pending, collected, failed
            sale_date=datetime.now(timezone.utc)
        )
        
        db.add(transaction_fee)
        
        # Mark listing as sold (inactive)
        listing.is_active = False
        listing.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(transaction_fee)
        
        logger.info(f"Casual sale recorded: {listing_id}, fee: ${fee_amount}, seller earnings: ${seller_earnings}")
        
        return {
            "message": "Sale recorded successfully",
            "transaction_id": transaction_fee.id,
            "sale_amount": float(sale_price),
            "fee_amount": float(fee_amount),
            "seller_earnings": float(seller_earnings),
            "fee_rate": f"{float(CASUAL_SELLER_FEE_RATE * 100)}%"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale price"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error recording casual sale: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record sale"
        )

@router.get("/my-fees")
async def get_my_transaction_fees(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's transaction fees"""
    try:
        fees = db.query(TransactionFee).filter(
            TransactionFee.user_id == current_user.id
        ).order_by(desc(TransactionFee.sale_date)).offset(skip).limit(limit).all()
        
        fee_list = []
        for fee in fees:
            # Get listing details
            listing = db.query(CasualListing).filter(
                CasualListing.id == fee.listing_id
            ).first()
            
            fee_list.append({
                "id": fee.id,
                "listing_title": listing.title if listing else "Unknown Item",
                "sale_amount": float(fee.sale_amount),
                "fee_amount": float(fee.fee_amount),
                "seller_earnings": float(fee.seller_earnings),
                "fee_rate": f"{float(fee.fee_rate * 100)}%",
                "fee_status": fee.fee_status,
                "sale_date": fee.sale_date.isoformat(),
                "buyer_id": fee.buyer_id
            })
        
        return {
            "fees": fee_list,
            "total_fees": len(fee_list)
        }
        
    except Exception as e:
        logger.error(f"Error fetching transaction fees: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch transaction fees"
        )

@router.get("/earnings-summary")
async def get_earnings_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's earnings summary from casual sales"""
    try:
        # Total earnings and fees
        totals = db.query(
            func.sum(TransactionFee.sale_amount).label('total_sales'),
            func.sum(TransactionFee.fee_amount).label('total_fees'),
            func.sum(TransactionFee.seller_earnings).label('total_earnings'),
            func.count(TransactionFee.id).label('total_transactions')
        ).filter(TransactionFee.user_id == current_user.id).first()
        
        # This month's earnings
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        monthly_totals = db.query(
            func.sum(TransactionFee.sale_amount).label('monthly_sales'),
            func.sum(TransactionFee.fee_amount).label('monthly_fees'),
            func.sum(TransactionFee.seller_earnings).label('monthly_earnings'),
            func.count(TransactionFee.id).label('monthly_transactions')
        ).filter(
            and_(
                TransactionFee.user_id == current_user.id,
                extract('month', TransactionFee.sale_date) == current_month,
                extract('year', TransactionFee.sale_date) == current_year
            )
        ).first()
        
        # Pending fees (not yet collected)
        pending_fees = db.query(
            func.sum(TransactionFee.fee_amount).label('pending_fees')
        ).filter(
            and_(
                TransactionFee.user_id == current_user.id,
                TransactionFee.fee_status == 'pending'
            )
        ).scalar() or Decimal('0')
        
        return {
            "all_time": {
                "total_sales": float(totals.total_sales or 0),
                "total_fees_owed": float(totals.total_fees or 0),
                "total_earnings": float(totals.total_earnings or 0),
                "total_transactions": totals.total_transactions or 0
            },
            "this_month": {
                "monthly_sales": float(monthly_totals.monthly_sales or 0),
                "monthly_fees_owed": float(monthly_totals.monthly_fees or 0),
                "monthly_earnings": float(monthly_totals.monthly_earnings or 0),
                "monthly_transactions": monthly_totals.monthly_transactions or 0
            },
            "pending": {
                "pending_fees": float(pending_fees),
                "fee_rate": f"{float(CASUAL_SELLER_FEE_RATE * 100)}%"
            }
        }
        
    except Exception as e:
        logger.error(f"Error calculating earnings summary: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate earnings summary"
        )

@router.post("/simulate-sale")
async def simulate_sale_calculation(
    sale_price: float,
    current_user: User = Depends(get_current_user)
):
    """Simulate a sale to show fees and earnings (for UI preview)"""
    try:
        if sale_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Sale price must be greater than 0"
            )
        
        price = Decimal(str(sale_price))
        fee_amount = price * CASUAL_SELLER_FEE_RATE
        seller_earnings = price - fee_amount
        
        return {
            "sale_price": float(price),
            "fee_rate": f"{float(CASUAL_SELLER_FEE_RATE * 100)}%",
            "fee_amount": float(fee_amount),
            "seller_earnings": float(seller_earnings),
            "earnings_percentage": f"{float((seller_earnings / price) * 100):.1f}%"
        }
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid sale price"
        )

# Admin endpoints (for fee collection and management)
@router.get("/admin/all-fees")
async def get_all_transaction_fees(
    skip: int = 0,
    limit: int = 100,
    fee_status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Admin: Get all transaction fees (admin only)"""
    if current_user.role != 'ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        query = db.query(TransactionFee)
        
        if fee_status:
            query = query.filter(TransactionFee.fee_status == fee_status)
        
        fees = query.order_by(desc(TransactionFee.sale_date)).offset(skip).limit(limit).all()
        
        fee_list = []
        for fee in fees:
            # Get seller and listing details
            seller = db.query(User).filter(User.id == fee.user_id).first()
            listing = db.query(CasualListing).filter(CasualListing.id == fee.listing_id).first()
            
            fee_list.append({
                "id": fee.id,
                "seller_name": f"{seller.first_name} {seller.last_name}" if seller else "Unknown",
                "seller_email": seller.email if seller else "Unknown",
                "listing_title": listing.title if listing else "Unknown Item",
                "sale_amount": float(fee.sale_amount),
                "fee_amount": float(fee.fee_amount),
                "fee_status": fee.fee_status,
                "sale_date": fee.sale_date.isoformat(),
                "buyer_id": fee.buyer_id
            })
        
        return {
            "fees": fee_list,
            "total": len(fee_list)
        }
        
    except Exception as e:
        logger.error(f"Error fetching all transaction fees: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch transaction fees"
        )

@router.put("/admin/update-fee-status/{fee_id}")
async def update_fee_status(
    fee_id: str,
    new_status: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Admin: Update transaction fee status"""
    if current_user.role != 'ADMIN':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    if new_status not in ['pending', 'collected', 'failed']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status must be 'pending', 'collected', or 'failed'"
        )
    
    try:
        fee = db.query(TransactionFee).filter(TransactionFee.id == fee_id).first()
        
        if not fee:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction fee not found"
            )
        
        fee.fee_status = new_status
        fee.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(f"Transaction fee {fee_id} status updated to {new_status}")
        
        return {"message": f"Fee status updated to {new_status}"}
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating fee status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update fee status"
        )