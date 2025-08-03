from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from pydantic import BaseModel
from datetime import datetime
from typing import List as TypingList

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from models.order import Order, OrderStatus, OrderItem, PaymentStatus
from models.shop import Shop
from models.user import User
from models.product import Product

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic schemas
class OrderItemResponse(BaseModel):
    id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price: float
    total_price: float

    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: str
    customer_id: str
    customer_name: str
    customer_email: str
    shop_id: str
    status: str
    payment_status: str
    total_amount: float
    shipping_address: str
    tracking_number: Optional[str] = None
    created_at: str
    updated_at: str
    items: List[OrderItemResponse]

    class Config:
        from_attributes = True

class OrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    tracking_number: Optional[str] = None

class CreateOrderItemRequest(BaseModel):
    product_id: str
    quantity: int

class CreateOrderRequest(BaseModel):
    items: TypingList[CreateOrderItemRequest]
    shipping_address: str
    payment_method: str = "card"

@router.post("/create", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    order_request: CreateOrderRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new order from cart items."""
    try:
        # Validate items and calculate total
        total_amount = 0
        order_items_data = []
        shop_id = None
        
        for item in order_request.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product {item.product_id} not found"
                )
            
            if not product.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Product {product.name} is not available"
                )
            
            if product.stock_quantity < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {product.name}. Available: {product.stock_quantity}"
                )
            
            # Get shop from product seller
            seller_shop = db.query(Shop).filter(Shop.owner_id == product.seller_id).first()
            if not seller_shop:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Shop not found for product {product.name}"
                )
            
            # For now, assume all items are from the same shop
            # In a real marketplace, you'd split orders by shop
            if shop_id is None:
                shop_id = seller_shop.id
            elif shop_id != seller_shop.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="All items must be from the same shop in this version"
                )
            
            item_total = float(product.price) * item.quantity
            total_amount += item_total
            
            order_items_data.append({
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': float(product.price),
                'total_price': item_total,
                'product': product
            })
        
        # Create order
        order = Order(
            customer_id=current_user.id,
            shop_id=shop_id,
            total_amount=total_amount,
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            shipping_address=order_request.shipping_address
        )
        
        db.add(order)
        db.flush()  # Get order ID
        
        # Create order items
        for item_data in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total_price=item_data['total_price']
            )
            db.add(order_item)
            
            # Update product stock
            product = item_data['product']
            product.stock_quantity -= item_data['quantity']
        
        db.commit()
        db.refresh(order)
        
        # Get customer info for response
        customer = db.query(User).filter(User.id == order.customer_id).first()
        
        # Get order items for response
        order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        items_response = []
        for item in order_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            items_response.append(OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name if product else "Unknown Product",
                quantity=item.quantity,
                unit_price=float(item.unit_price),
                total_price=float(item.total_price)
            ))
        
        response = OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
            customer_email=customer.email if customer else "unknown@email.com",
            shop_id=order.shop_id,
            status=order.status.value,
            payment_status=order.payment_status.value,
            total_amount=float(order.total_amount),
            shipping_address=order.shipping_address or "No address provided",
            tracking_number=order.tracking_number,
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat(),
            items=items_response
        )
        
        logger.info(f"Order created: {order.id} for customer {current_user.id}")
        return response
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating order: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )

@router.get("/shop-owner/orders", response_model=List[OrderResponse])
def get_shop_owner_orders(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get orders for the shop owner's shop."""
    try:
        # Get the shop for current user
        shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
        if not shop:
            return []
        
        # Build query
        query = db.query(Order).filter(Order.shop_id == shop.id)
        
        # Apply filters
        if status:
            try:
                order_status = OrderStatus(status)
                query = query.filter(Order.status == order_status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid order status: {status}"
                )
        
        if search:
            query = query.join(User).filter(
                (Order.id.contains(search)) |
                (User.first_name.contains(search)) |
                (User.last_name.contains(search)) |
                (User.email.contains(search))
            )
        
        # Pagination
        offset = (page - 1) * limit
        orders = query.order_by(Order.created_at.desc()).offset(offset).limit(limit).all()
        
        # Transform to response format
        result = []
        for order in orders:
            customer = db.query(User).filter(User.id == order.customer_id).first()
            order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
            
            items_response = []
            for item in order_items:
                product = db.query(Product).filter(Product.id == item.product_id).first()
                items_response.append(OrderItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=product.name if product else "Unknown Product",
                    quantity=item.quantity,
                    unit_price=float(item.unit_price),
                    total_price=float(item.total_price)
                ))
            
            result.append(OrderResponse(
                id=order.id,
                customer_id=order.customer_id,
                customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
                customer_email=customer.email if customer else "unknown@email.com",
                shop_id=order.shop_id,
                status=order.status.value,
                payment_status=order.payment_status.value,
                total_amount=float(order.total_amount),
                shipping_address=order.shipping_address or "No address provided",
                tracking_number=order.tracking_number,
                created_at=order.created_at.isoformat(),
                updated_at=order.updated_at.isoformat(),
                items=items_response
            ))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop owner orders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve orders"
        )

@router.get("/shop-owner/orders/stats")
def get_order_stats(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get order statistics for shop owner."""
    try:
        # Get the shop for current user
        shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
        if not shop:
            return {
                "total_orders": 0,
                "pending_orders": 0,
                "completed_orders": 0,
                "cancelled_orders": 0,
                "total_revenue": 0.0
            }
        
        # Get statistics
        from sqlalchemy import func
        
        total_orders = db.query(Order).filter(Order.shop_id == shop.id).count()
        pending_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            Order.status.in_([OrderStatus.PENDING, OrderStatus.PROCESSING])
        ).count()
        completed_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            Order.status == OrderStatus.DELIVERED
        ).count()
        cancelled_orders = db.query(Order).filter(
            Order.shop_id == shop.id,
            Order.status == OrderStatus.CANCELLED
        ).count()
        
        total_revenue = db.query(func.sum(Order.total_amount)).filter(
            Order.shop_id == shop.id,
            Order.status == OrderStatus.DELIVERED
        ).scalar() or 0.0
        
        return {
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,
            "cancelled_orders": cancelled_orders,
            "total_revenue": float(total_revenue)
        }
        
    except Exception as e:
        logger.error(f"Error getting order stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve order statistics"
        )

@router.patch("/{order_id}/status")
def update_order_status(
    order_id: str,
    update_request: OrderUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update order status (shop owner only)."""
    try:
        # Get the shop for current user
        shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
        if not shop:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have a shop"
            )
        
        # Get the order
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.shop_id == shop.id
        ).first()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Update status if provided
        if update_request.status:
            try:
                new_status = OrderStatus(update_request.status)
                order.status = new_status
                order.updated_at = datetime.utcnow()
                
                # Create notification for customer
                from services.notification import create_order_notification
                create_order_notification(db, order.customer_id, order_id, update_request.status)
                
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid order status: {update_request.status}"
                )
        
        # Update tracking number if provided
        if update_request.tracking_number:
            order.tracking_number = update_request.tracking_number
            order.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(order)
        
        return {"message": "Order updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating order status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order"
        )

@router.get("/{order_id}", response_model=OrderResponse)
def get_order_details(
    order_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed order information."""
    try:
        # Check if user owns the shop or is the customer
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Check permissions
        shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
        if order.customer_id != current_user.id and (not shop or shop.owner_id != current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this order"
            )
        
        # Get customer and items data
        customer = db.query(User).filter(User.id == order.customer_id).first()
        order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
        
        items_response = []
        for item in order_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            items_response.append(OrderItemResponse(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name if product else "Unknown Product",
                quantity=item.quantity,
                unit_price=float(item.unit_price),
                total_price=float(item.total_price)
            ))
        
        return OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
            customer_email=customer.email if customer else "unknown@email.com",
            shop_id=order.shop_id,
            status=order.status.value,
            payment_status=order.payment_status.value,
            total_amount=float(order.total_amount),
            shipping_address=order.shipping_address or "No address provided",
            tracking_number=order.tracking_number,
            created_at=order.created_at.isoformat(),
            updated_at=order.updated_at.isoformat(),
            items=items_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting order details: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve order details"
        )