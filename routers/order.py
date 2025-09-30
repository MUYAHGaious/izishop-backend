from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
from pydantic import BaseModel
from datetime import datetime
from typing import List as TypingList

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from models.order import Order, OrderStatus, OrderItem, PaymentStatus, OrderStatusHistory
from models.shop import Shop
from models.user import User
from models.product import Product
import uuid

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

class OrderStatusUpdateRequest(BaseModel):
    new_status: str
    notes: Optional[str] = None
    carrier: Optional[str] = None
    estimated_delivery_date: Optional[str] = None

class OrderStatusHistoryResponse(BaseModel):
    id: str
    old_status: Optional[str] = None
    new_status: str
    changed_by: Optional[str] = None
    changed_at: str
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class CreateOrderItemRequest(BaseModel):
    product_id: str
    quantity: int

class CreateOrderRequest(BaseModel):
    items: TypingList[CreateOrderItemRequest]
    shipping_address: str
    payment_method: str = "card"

class CreateMultiVendorOrderRequest(BaseModel):
    items: TypingList[CreateOrderItemRequest]
    shipping_address: str
    payment_method: str = "card"

class MultiVendorOrderResponse(BaseModel):
    master_order_id: str
    customer_id: str
    customer_name: str
    total_amount: float
    status: str
    payment_status: str
    shipping_address: str
    created_at: str
    vendor_orders: List[OrderResponse]
    vendor_count: int
    total_items: int

    class Config:
        from_attributes = True

@router.post("/create", response_model=OrderResponse, status_code=http_status.HTTP_201_CREATED)
def create_order(
    order_request: CreateOrderRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new order from cart items - OPTIMIZED VERSION."""
    try:
        # OPTIMIZATION: Get all product IDs upfront and fetch in one query
        product_ids = [item.product_id for item in order_request.items]

        # OPTIMIZATION: Single query to get all products with their seller shops
        products_with_shops = db.query(Product, Shop).join(
            Shop, Shop.owner_id == Product.seller_id
        ).filter(
            Product.id.in_(product_ids),
            Product.is_active == True
        ).all()

        # Convert to dictionary for fast lookup
        product_shop_map = {product.id: (product, shop) for product, shop in products_with_shops}

        # Validate all items exist and are available
        total_amount = 0
        order_items_data = []
        shop_id = None

        for item in order_request.items:
            if item.product_id not in product_shop_map:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Product {item.product_id} not found or not available"
                )

            product, seller_shop = product_shop_map[item.product_id]

            if product.stock_quantity < item.quantity:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {product.name}. Available: {product.stock_quantity}"
                )

            # For now, assume all items are from the same shop
            if shop_id is None:
                shop_id = seller_shop.id
            elif shop_id != seller_shop.id:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="All items must be from the same shop in this version"
                )

            item_total = float(product.price) * item.quantity
            total_amount += item_total

            order_items_data.append({
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': float(product.price),
                'total_price': item_total,
                'product_name': product.name,
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

        # OPTIMIZATION: Batch create order items
        order_items = []
        for item_data in order_items_data:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item_data['product_id'],
                quantity=item_data['quantity'],
                unit_price=item_data['unit_price'],
                total_price=item_data['total_price']
            )
            order_items.append(order_item)
            db.add(order_item)

            # Update product stock
            product = item_data['product']
            product.stock_quantity -= item_data['quantity']

        db.commit()

        # OPTIMIZATION: Build response without additional queries
        items_response = []
        for i, order_item in enumerate(order_items):
            items_response.append(OrderItemResponse(
                id=order_item.id,
                product_id=order_item.product_id,
                product_name=order_items_data[i]['product_name'],
                quantity=order_item.quantity,
                unit_price=float(order_item.unit_price),
                total_price=float(order_item.total_price)
            ))

        response = OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            customer_name=f"{current_user.first_name} {current_user.last_name}",
            customer_email=current_user.email,
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
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )

@router.post("/create-multi-vendor", response_model=MultiVendorOrderResponse, status_code=http_status.HTTP_201_CREATED)
def create_multi_vendor_order(
    order_request: CreateMultiVendorOrderRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a multi-vendor order by splitting cart items by vendor."""
    try:
        logger.info(f"Creating multi-vendor order for customer {current_user.id}")

        # OPTIMIZATION: Extract all product IDs first
        product_ids = [item.product_id for item in order_request.items]

        # OPTIMIZATION: Single query to get all products with their seller shops
        products_with_shops = db.query(Product, Shop).join(
            Shop, Shop.owner_id == Product.seller_id
        ).filter(
            Product.id.in_(product_ids),
            Product.is_active == True
        ).all()

        # Convert to dictionary for fast lookup
        product_shop_map = {product.id: (product, shop) for product, shop in products_with_shops}

        # Validate all products exist and are available
        for item in order_request.items:
            if item.product_id not in product_shop_map:
                raise HTTPException(
                    status_code=http_status.HTTP_404_NOT_FOUND,
                    detail=f"Product {item.product_id} not found or not available"
                )

            product, shop = product_shop_map[item.product_id]

            if product.stock_quantity < item.quantity:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {product.name}. Available: {product.stock_quantity}"
                )

        # Group items by vendor/shop
        vendor_groups = {}
        total_amount = 0

        for item in order_request.items:
            product, seller_shop = product_shop_map[item.product_id]
            vendor_id = seller_shop.id

            # Group items by vendor
            if vendor_id not in vendor_groups:
                vendor_groups[vendor_id] = {
                    'shop': seller_shop,
                    'items': [],
                    'subtotal': 0
                }

            item_total = float(product.price) * item.quantity
            vendor_groups[vendor_id]['subtotal'] += item_total
            total_amount += item_total

            vendor_groups[vendor_id]['items'].append({
                'product_id': item.product_id,
                'quantity': item.quantity,
                'unit_price': float(product.price),
                'total_price': item_total,
                'product': product
            })
        
        # Create master order (for tracking purposes)
        master_order = Order(
            customer_id=current_user.id,
            shop_id=None,  # Master order doesn't belong to a specific shop
            total_amount=total_amount,
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            shipping_address=order_request.shipping_address,
            notes=f"Multi-vendor order with {len(vendor_groups)} vendors"
        )
        
        db.add(master_order)
        db.flush()  # Get master order ID
        
        # Create vendor-specific orders
        vendor_orders = []
        total_items = 0
        
        for vendor_id, vendor_data in vendor_groups.items():
            # Create vendor order
            vendor_order = Order(
                customer_id=current_user.id,
                shop_id=vendor_id,
                total_amount=vendor_data['subtotal'],
                status=OrderStatus.PENDING,
                payment_status=PaymentStatus.PENDING,
                shipping_address=order_request.shipping_address,
                notes=f"Vendor order from master order {master_order.id}"
            )
            
            db.add(vendor_order)
            db.flush()  # Get vendor order ID
            
            # Create order items for this vendor
            for item_data in vendor_data['items']:
                order_item = OrderItem(
                    order_id=vendor_order.id,
                    product_id=item_data['product_id'],
                    quantity=item_data['quantity'],
                    unit_price=item_data['unit_price'],
                    total_price=item_data['total_price']
                )
                db.add(order_item)
                
                # Update product stock
                product = item_data['product']
                product.stock_quantity -= item_data['quantity']
                total_items += item_data['quantity']
            
            vendor_orders.append(vendor_order)
        
        # OPTIMIZATION: Batch query for all shop owners to send notifications
        shop_ids = [vendor_order.shop_id for vendor_order in vendor_orders]
        shops_with_owners = db.query(Shop, User).join(
            User, User.id == Shop.owner_id
        ).filter(Shop.id.in_(shop_ids)).all()

        shop_owner_map = {shop.id: (shop, owner) for shop, owner in shops_with_owners}

        # Send notifications to vendors
        notifications_to_create = []
        for vendor_order in vendor_orders:
            if vendor_order.shop_id in shop_owner_map:
                shop, vendor = shop_owner_map[vendor_order.shop_id]

                # Create notification for vendor
                from models.notification import Notification, NotificationType, NotificationPriority

                notification = Notification(
                    user_id=vendor.id,
                    type=NotificationType.ORDER,
                    title="🛍️ New Order Received!",
                    message=f"""You have received a new order!

📦 ORDER DETAILS:
• Order ID: {vendor_order.id}
• Total Amount: ${vendor_order.total_amount}
• Items: {len(vendor_order.items)} items
• Customer: Order from master order {master_order.id}

🚀 NEXT STEPS:
1. Review order details in your dashboard
2. Prepare items for shipping
3. Update order status when ready to ship

Need help? Contact our support team anytime!

IziShopin Team 🚀""",
                    related_id=vendor_order.id,
                    related_type="new_order",
                    priority=NotificationPriority.HIGH,
                    action_url=f"/shop-owner-dashboard/orders/{vendor_order.id}",
                    action_label="View Order",
                    icon="ShoppingCart"
                )

                notifications_to_create.append(notification)
                logger.info(f"Created order notification for vendor {vendor.email}")

        # OPTIMIZATION: Batch insert all notifications
        if notifications_to_create:
            db.add_all(notifications_to_create)
        
        db.commit()
        db.refresh(master_order)
        
        # Get customer info for response
        customer = db.query(User).filter(User.id == master_order.customer_id).first()
        
        # OPTIMIZATION: Batch query for all order items and products
        vendor_order_ids = [vendor_order.id for vendor_order in vendor_orders]
        order_items_with_products = db.query(OrderItem, Product).join(
            Product, Product.id == OrderItem.product_id
        ).filter(OrderItem.order_id.in_(vendor_order_ids)).all()

        # Group order items by order_id for fast lookup
        order_items_map = {}
        for order_item, product in order_items_with_products:
            if order_item.order_id not in order_items_map:
                order_items_map[order_item.order_id] = []
            order_items_map[order_item.order_id].append((order_item, product))

        # Build vendor order responses
        vendor_order_responses = []
        for vendor_order in vendor_orders:
            # Build item responses from pre-fetched data
            items_response = []
            if vendor_order.id in order_items_map:
                for order_item, product in order_items_map[vendor_order.id]:
                    items_response.append(OrderItemResponse(
                        id=order_item.id,
                        product_id=order_item.product_id,
                        product_name=product.name if product else "Unknown Product",
                        quantity=order_item.quantity,
                        unit_price=float(order_item.unit_price),
                        total_price=float(order_item.total_price)
                    ))

            vendor_order_responses.append(OrderResponse(
                id=vendor_order.id,
                customer_id=vendor_order.customer_id,
                customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
                customer_email=customer.email if customer else "unknown@email.com",
                shop_id=vendor_order.shop_id,
                status=vendor_order.status.value,
                payment_status=vendor_order.payment_status.value,
                total_amount=float(vendor_order.total_amount),
                shipping_address=vendor_order.shipping_address or "No address provided",
                tracking_number=vendor_order.tracking_number,
                created_at=vendor_order.created_at.isoformat(),
                updated_at=vendor_order.updated_at.isoformat(),
                items=items_response
            ))
        
        # Build response
        response = MultiVendorOrderResponse(
            master_order_id=master_order.id,
            customer_id=master_order.customer_id,
            customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
            total_amount=float(master_order.total_amount),
            status=master_order.status.value,
            payment_status=master_order.payment_status.value,
            shipping_address=master_order.shipping_address,
            created_at=master_order.created_at.isoformat(),
            vendor_orders=vendor_order_responses,
            vendor_count=len(vendor_orders),
            total_items=total_items
        )
        
        logger.info(f"Multi-vendor order created: {master_order.id} with {len(vendor_orders)} vendor orders")
        return response
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating multi-vendor order: {str(e)}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create multi-vendor order"
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
                    status_code=http_status.HTTP_400_BAD_REQUEST,
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
            status_code=500,
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
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="You don't have a shop"
            )
        
        # Get the order
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.shop_id == shop.id
        ).first()
        
        if not order:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Update status if provided
        if update_request.status:
            try:
                new_status = OrderStatus(update_request.status)
                old_status = order.status.value

                # Create status history record
                history_record = OrderStatusHistory(
                    id=str(uuid.uuid4()),
                    order_id=order.id,
                    old_status=old_status,
                    new_status=new_status.value,
                    changed_by=current_user.id,
                    changed_at=datetime.utcnow(),
                    notes=f"Status updated by shop owner"
                )
                db.add(history_record)

                # Update order
                order.status = new_status
                order.status_updated_at = datetime.utcnow()
                order.updated_at = datetime.utcnow()

                # Create notification for customer
                try:
                    from services.notification import create_order_notification
                    create_order_notification(db, order.customer_id, order_id, update_request.status)
                except ImportError:
                    # Notification service not available, continue without it
                    logger.warning("Notification service not available")

            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
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
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Check permissions
        shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
        if order.customer_id != current_user.id and (not shop or shop.owner_id != current_user.id):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
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
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve order details"
        )

@router.put("/{order_id}/status", status_code=http_status.HTTP_200_OK)
def update_order_status_enhanced(
    order_id: str,
    status_update: OrderStatusUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enhanced order status update with full tracking and history."""
    try:
        # Get the shop for current user
        shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
        if not shop:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="You don't have a shop"
            )

        # Get the order
        order = db.query(Order).filter(
            Order.id == order_id,
            Order.shop_id == shop.id
        ).first()

        if not order:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # Validate new status
        try:
            new_status = OrderStatus(status_update.new_status)
        except ValueError:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid order status: {status_update.new_status}"
            )

        # Store old status for history
        old_status = order.status.value

        # Create status history record
        history_record = OrderStatusHistory(
            id=str(uuid.uuid4()),
            order_id=order.id,
            old_status=old_status,
            new_status=new_status.value,
            changed_by=current_user.id,
            changed_at=datetime.utcnow(),
            notes=status_update.notes or f"Status updated from {old_status} to {new_status.value}"
        )
        db.add(history_record)

        # Update order
        order.status = new_status
        order.status_updated_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()

        # Update additional fields if provided
        if status_update.carrier:
            order.carrier = status_update.carrier

        if status_update.estimated_delivery_date:
            try:
                from datetime import datetime as dt
                order.estimated_delivery_date = dt.fromisoformat(status_update.estimated_delivery_date)
            except ValueError:
                # If date parsing fails, just log it and continue
                logger.warning(f"Invalid delivery date format: {status_update.estimated_delivery_date}")

        db.commit()
        db.refresh(order)

        return {
            "message": "Order status updated successfully",
            "order_id": order.id,
            "old_status": old_status,
            "new_status": new_status.value,
            "status_updated_at": order.status_updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating order status: {str(e)}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order status"
        )

@router.get("/{order_id}/history", response_model=List[OrderStatusHistoryResponse])
def get_order_status_history(
    order_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the complete status history for an order."""
    try:
        # Get the order and check permissions
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        # Check if user is either the customer or the shop owner
        shop = db.query(Shop).filter(Shop.id == order.shop_id).first()
        if order.customer_id != current_user.id and (not shop or shop.owner_id != current_user.id):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to view this order's history"
            )

        # Get status history
        history = db.query(OrderStatusHistory).filter(
            OrderStatusHistory.order_id == order_id
        ).order_by(OrderStatusHistory.changed_at.asc()).all()

        # Transform to response format
        result = []
        for record in history:
            result.append(OrderStatusHistoryResponse(
                id=record.id,
                old_status=record.old_status,
                new_status=record.new_status,
                changed_by=record.changed_by,
                changed_at=record.changed_at.isoformat(),
                notes=record.notes
            ))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting order status history: {str(e)}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve order status history"
        )

# Order Cancellation Endpoints
@router.get("/{order_id}/cancellation-policy")
async def get_order_cancellation_policy(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Check if order can be cancelled and get cancellation policy"""
    try:
        # Import here to avoid circular imports
        from services.order_cancellation_service import OrderCancellationService

        cancellation_service = OrderCancellationService(db)
        policy = cancellation_service.check_cancellation_policy(order_id, current_user.id)

        return {
            "can_cancel": policy.can_cancel,
            "reason": policy.reason
        }
    except Exception as e:
        logger.error(f"Error checking cancellation policy for order {order_id}: {str(e)}")
        return {
            "can_cancel": False,
            "reason": "System error. Please try again later."
        }

@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel an order with full refund processing"""
    try:
        # Import here to avoid circular imports
        from services.order_cancellation_service import OrderCancellationService
        from schemas.order_cancellation import CancellationRequest

        # For now, use default cancellation data
        cancellation_data = {
            "reason": "customer_changed_mind",
            "description": "Order cancelled via API",
            "refund_requested": True,
            "restock_items": True
        }

        cancellation_service = OrderCancellationService(db)
        result = cancellation_service.cancel_order(order_id, current_user.id, cancellation_data)

        return {
            "success": result.success,
            "message": result.message,
            "cancellation_id": result.cancellation_id,
            "refund_amount": result.refund_amount
        }
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return {
            "success": False,
            "message": "Failed to cancel order. Please try again."
        }