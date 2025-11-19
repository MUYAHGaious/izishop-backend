from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
import logging
from pydantic import BaseModel
from datetime import datetime
from typing import List as TypingList
from collections import defaultdict

from database.connection import get_db
from routers.auth import get_current_user
from schemas.user import UserResponse
from models.order import Order, OrderStatus, OrderItem, PaymentStatus, OrderStatusHistory
from models.shop import Shop
from models.user import User
from models.product import Product
from models.casual_listing import CasualListing
import uuid

logger = logging.getLogger(__name__)
router = APIRouter()

# Updated to support casual marketplace listings

# Optimized schemas
class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int

class CreateOrderRequest(BaseModel):
    items: List[OrderItemRequest]
    shipping_address: str
    payment_method: str = "card"
    notes: Optional[str] = None

class OrderItemResponse(BaseModel):
    id: str
    product_id: str  # Unified ID - references either products.id or casual_listings.id
    product_type: str  # "regular" or "casual" - identifies which table the product_id references
    product_name: str
    product_image: Optional[str] = None
    quantity: int
    unit_price: float
    total_price: float
    shop_id: Optional[str] = None  # NULL for casual sellers
    shop_name: str

    class Config:
        from_attributes = True

class VendorOrderResponse(BaseModel):
    id: str
    shop_id: Optional[str] = None  # NULL for casual sellers without shops
    shop_name: str
    shop_owner_id: str
    customer_id: str
    customer_name: str
    customer_email: str
    status: str
    payment_status: str
    total_amount: float
    shipping_address: str
    tracking_number: Optional[str] = None
    created_at: str
    updated_at: str
    items: List[OrderItemResponse]
    item_count: int

    class Config:
        from_attributes = True

class OptimizedOrderResponse(BaseModel):
    """Unified response that works for both single and multi-vendor orders"""
    order_id: str  # Main order ID (single order) or master order ID (multi-vendor)
    customer_id: str
    customer_name: str
    customer_email: str
    total_amount: float
    status: str
    payment_status: str
    shipping_address: str
    created_at: str
    order_type: str  # "single_vendor" or "multi_vendor"

    # Single vendor fields (used when order_type = "single_vendor")
    shop_id: Optional[str] = None
    shop_name: Optional[str] = None
    items: Optional[List[OrderItemResponse]] = []

    # Multi-vendor fields (used when order_type = "multi_vendor")
    vendor_orders: Optional[List[VendorOrderResponse]] = []
    vendor_count: Optional[int] = 0
    total_items: Optional[int] = 0

    class Config:
        from_attributes = True

class CustomerOrdersResponse(BaseModel):
    """Response wrapper for customer orders with pagination info"""
    orders: List[OptimizedOrderResponse]
    total: int
    page: int
    totalPages: int

    class Config:
        from_attributes = True

@router.post("/create", response_model=OptimizedOrderResponse, status_code=http_status.HTTP_201_CREATED)
async def create_order_optimized(
    order_request: CreateOrderRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Optimized unified order creation endpoint.
    Automatically handles both single and multi-vendor orders intelligently.
    """
    try:
        logger.info(f"🛍️ Creating optimized order for customer {current_user.id} with {len(order_request.items)} items")

        # Step 1: Validate and group items by shop
        vendor_groups = defaultdict(lambda: {"items": [], "subtotal": 0, "shop": None})
        total_amount = 0

        for item_request in order_request.items:
            # Try to get product from regular products first
            product = db.query(Product).filter(
                Product.id == item_request.product_id,
                Product.is_active == True
            ).first()

            # If not found in products, try casual listings
            casual_listing = None
            is_casual = False
            if not product:
                casual_listing = db.query(CasualListing).filter(
                    CasualListing.id == item_request.product_id,
                    CasualListing.status == "active"
                ).first()

                if not casual_listing:
                    raise HTTPException(
                        status_code=http_status.HTTP_404_NOT_FOUND,
                        detail=f"Product {item_request.product_id} not found or inactive"
                    )
                is_casual = True

            # Get product details based on type
            if is_casual:
                product_name = casual_listing.title
                product_price = casual_listing.price
                product_stock = 1  # Casual listings are one-of-a-kind
                seller_id = casual_listing.seller_id
                product_image = casual_listing.image_urls[0] if casual_listing.image_urls else None
            else:
                product_name = product.name
                product_price = product.price
                product_stock = product.stock_quantity
                seller_id = product.seller_id
                product_image = product.image_urls[0] if product.image_urls else None

            # Validate stock
            if product_stock < item_request.quantity:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Insufficient stock for {product_name}. Available: {product_stock}, Requested: {item_request.quantity}"
                )

            # Get shop information (cached query)
            # For casual sellers, create a virtual shop entry
            if not vendor_groups[seller_id]["shop"]:
                shop = db.query(Shop).filter(Shop.owner_id == seller_id).first()
                if not shop:
                    # For casual sellers without a shop, create a virtual shop representation
                    if is_casual:
                        seller = db.query(User).filter(User.id == seller_id).first()
                        vendor_groups[seller_id]["shop"] = {
                            "id": seller_id,
                            "name": f"{seller.first_name} {seller.last_name}".strip() if seller else "Individual Seller",
                            "is_casual_seller": True
                        }
                    else:
                        raise HTTPException(
                            status_code=http_status.HTTP_400_BAD_REQUEST,
                            detail=f"Shop not found for product {product_name}"
                        )
                else:
                    vendor_groups[seller_id]["shop"] = shop

            # Calculate item total
            item_total = float(product_price) * item_request.quantity
            total_amount += item_total

            # Add to vendor group
            vendor_groups[seller_id]["items"].append({
                "product": product if not is_casual else casual_listing,
                "is_casual": is_casual,
                "quantity": item_request.quantity,
                "unit_price": float(product_price),
                "total_price": item_total,
                "product_name": product_name,
                "product_image": product_image
            })
            vendor_groups[seller_id]["subtotal"] += item_total

        # Step 2: Determine order type and create accordingly
        vendor_count = len(vendor_groups)
        is_multi_vendor = vendor_count > 1

        logger.info(f"📊 Order analysis: {vendor_count} vendors detected, multi-vendor: {is_multi_vendor}")

        if is_multi_vendor:
            return await _create_multi_vendor_order(db, current_user, order_request, vendor_groups, total_amount)
        else:
            return await _create_single_vendor_order(db, current_user, order_request, vendor_groups, total_amount)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error creating optimized order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )

async def _create_single_vendor_order(
    db: Session,
    current_user: UserResponse,
    order_request: CreateOrderRequest,
    vendor_groups: Dict,
    total_amount: float
) -> OptimizedOrderResponse:
    """Create a single vendor order"""
    logger.info("🏪 Creating single vendor order")

    # Get the single vendor
    vendor_id = list(vendor_groups.keys())[0]
    vendor_data = vendor_groups[vendor_id]
    shop = vendor_data["shop"]

    # Check if shop is a dict (casual seller) or Shop object
    is_casual_seller = isinstance(shop, dict) and shop.get("is_casual_seller", False)
    shop_id = None if is_casual_seller else shop.id  # NULL for casual sellers
    shop_name = shop["name"] if is_casual_seller else shop.name

    # Create order
    order = Order(
        customer_id=current_user.id,
        shop_id=shop_id,  # Will be NULL for casual sellers
        total_amount=total_amount,
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING,
        shipping_address=order_request.shipping_address,
        notes=order_request.notes
    )

    db.add(order)
    db.flush()

    # Create order items and update stock
    items_response = []
    for item_data in vendor_data["items"]:
        # Set product_id or casual_listing_id based on item type
        is_casual = item_data.get("is_casual", False)
        order_item = OrderItem(
            order_id=order.id,
            product_id=None if is_casual else item_data["product"].id,
            casual_listing_id=item_data["product"].id if is_casual else None,
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            total_price=item_data["total_price"]
        )
        db.add(order_item)

        # Update stock based on product type
        if item_data.get("is_casual", False):
            # For casual listings, mark as sold
            item_data["product"].status = "sold"
            item_data["product"].sold_at = datetime.utcnow()
        else:
            # For regular products, decrease stock
            item_data["product"].stock_quantity -= item_data["quantity"]

        # Build response item
        items_response.append(OrderItemResponse(
            id=str(uuid.uuid4()),  # Temporary ID for response
            product_id=item_data["product"].id,
            product_type="casual" if item_data.get("is_casual", False) else "regular",
            product_name=item_data.get("product_name", "Unknown Product"),
            product_image=item_data.get("product_image"),
            quantity=item_data["quantity"],
            unit_price=item_data["unit_price"],
            total_price=item_data["total_price"],
            shop_id=shop_id,
            shop_name=shop_name
        ))

    # Send notification to shop owner (skip for casual sellers for now)
    if not is_casual_seller:
        _send_vendor_notification(db, shop, order, len(vendor_data["items"]))

    db.commit()
    db.refresh(order)

    # Get customer info
    customer = db.query(User).filter(User.id == current_user.id).first()

    return OptimizedOrderResponse(
        order_id=order.id,
        customer_id=order.customer_id,
        customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
        customer_email=customer.email if customer else "unknown@email.com",
        total_amount=float(order.total_amount),
        status=order.status.value,
        payment_status=order.payment_status.value,
        shipping_address=order.shipping_address,
        created_at=order.created_at.isoformat(),
        order_type="single_vendor",
        shop_id=shop_id,
        shop_name=shop_name,
        items=items_response
    )

async def _create_multi_vendor_order(
    db: Session,
    current_user: UserResponse,
    order_request: CreateOrderRequest,
    vendor_groups: Dict,
    total_amount: float
) -> OptimizedOrderResponse:
    """Create a multi-vendor order with separate orders per vendor"""
    logger.info(f"🏪🏪 Creating multi-vendor order with {len(vendor_groups)} vendors")

    # Create master order for tracking
    master_order = Order(
        customer_id=current_user.id,
        shop_id=None,  # No specific shop for master order
        total_amount=total_amount,
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING,
        shipping_address=order_request.shipping_address,
        notes=f"Multi-vendor order with {len(vendor_groups)} vendors: {order_request.notes or ''}"
    )

    db.add(master_order)
    db.flush()

    # Create individual vendor orders
    vendor_orders_response = []
    total_items = 0

    for vendor_id, vendor_data in vendor_groups.items():
        shop = vendor_data["shop"]

        # Check if shop is a dict (casual seller) or Shop object
        is_casual_seller = isinstance(shop, dict) and shop.get("is_casual_seller", False)
        shop_id = None if is_casual_seller else shop.id  # NULL for casual sellers
        shop_name = shop["name"] if is_casual_seller else shop.name
        shop_owner_id = shop["id"] if is_casual_seller else shop.owner_id

        # Create vendor-specific order
        vendor_order = Order(
            customer_id=current_user.id,
            shop_id=shop_id,  # Will be NULL for casual sellers
            total_amount=vendor_data["subtotal"],
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            shipping_address=order_request.shipping_address,
            notes=f"Part of multi-vendor order {master_order.id}: {order_request.notes or ''}"
        )

        db.add(vendor_order)
        db.flush()

        # Create order items for this vendor
        items_response = []
        for item_data in vendor_data["items"]:
            # Set product_id or casual_listing_id based on item type
            is_casual = item_data.get("is_casual", False)
            order_item = OrderItem(
                order_id=vendor_order.id,
                product_id=None if is_casual else item_data["product"].id,
                casual_listing_id=item_data["product"].id if is_casual else None,
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                total_price=item_data["total_price"]
            )
            db.add(order_item)

            # Update stock based on product type
            if item_data.get("is_casual", False):
                # For casual listings, mark as sold
                item_data["product"].status = "sold"
                item_data["product"].sold_at = datetime.utcnow()
            else:
                # For regular products, decrease stock
                item_data["product"].stock_quantity -= item_data["quantity"]

            total_items += item_data["quantity"]

            # Build response item
            items_response.append(OrderItemResponse(
                id=str(uuid.uuid4()),  # Temporary ID for response
                product_id=item_data["product"].id,
                product_type="casual" if item_data.get("is_casual", False) else "regular",
                product_name=item_data.get("product_name", "Unknown Product"),
                product_image=item_data.get("product_image"),
                quantity=item_data["quantity"],
                unit_price=item_data["unit_price"],
                total_price=item_data["total_price"],
                shop_id=shop_id,
                shop_name=shop_name
            ))

        # Send notification to vendor (skip for casual sellers)
        if not is_casual_seller:
            _send_vendor_notification(db, shop, vendor_order, len(vendor_data["items"]))

        # Get shop owner info
        shop_owner = db.query(User).filter(User.id == shop_owner_id).first() if not is_casual_seller else None
        customer = db.query(User).filter(User.id == current_user.id).first()

        # Build vendor order response
        vendor_orders_response.append(VendorOrderResponse(
            id=vendor_order.id,
            shop_id=shop_id,
            shop_name=shop_name,
            shop_owner_id=shop_owner_id,
            customer_id=vendor_order.customer_id,
            customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
            customer_email=customer.email if customer else "unknown@email.com",
            status=vendor_order.status.value,
            payment_status=vendor_order.payment_status.value,
            total_amount=float(vendor_order.total_amount),
            shipping_address=vendor_order.shipping_address,
            tracking_number=vendor_order.tracking_number,
            created_at=vendor_order.created_at.isoformat(),
            updated_at=vendor_order.updated_at.isoformat(),
            items=items_response,
            item_count=len(items_response)
        ))

    db.commit()
    db.refresh(master_order)

    # Get customer info
    customer = db.query(User).filter(User.id == current_user.id).first()

    return OptimizedOrderResponse(
        order_id=master_order.id,
        customer_id=master_order.customer_id,
        customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
        customer_email=customer.email if customer else "unknown@email.com",
        total_amount=float(master_order.total_amount),
        status=master_order.status.value,
        payment_status=master_order.payment_status.value,
        shipping_address=master_order.shipping_address,
        created_at=master_order.created_at.isoformat(),
        order_type="multi_vendor",
        vendor_orders=vendor_orders_response,
        vendor_count=len(vendor_orders_response),
        total_items=total_items
    )

def _send_vendor_notification(db: Session, shop: Shop, order: Order, item_count: int):
    """Send notification to vendor about new order"""
    try:
        from models.notification import Notification, NotificationType, NotificationPriority

        vendor = db.query(User).filter(User.id == shop.owner_id).first()
        if vendor:
            notification = Notification(
                user_id=vendor.id,
                type=NotificationType.ORDER,
                title="🛍️ New Order Received!",
                message=f"""New order received for {shop.name}!

📦 ORDER DETAILS:
• Order ID: {order.id}
• Total Amount: ${order.total_amount}
• Items: {item_count} items
• Customer: {order.shipping_address}

🚀 NEXT STEPS:
1. Review order details in your dashboard
2. Prepare items for shipping
3. Update order status when ready

Visit your dashboard to manage this order!""",
                related_id=order.id,
                related_type="new_order",
                priority=NotificationPriority.HIGH,
                action_url=f"/shop-owner-dashboard/orders/{order.id}",
                action_label="View Order",
                icon="ShoppingCart"
            )

            db.add(notification)
            logger.info(f"✅ Created notification for vendor {vendor.email}")
    except Exception as e:
        logger.error(f"❌ Failed to send vendor notification: {e}")
        # Don't fail the order creation if notification fails

@router.get("/shop-owner/orders", response_model=List[VendorOrderResponse])
def get_shop_owner_orders_optimized(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get orders for the shop owner's shop - optimized version"""
    try:
        # Get the shop for current user
        shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
        if not shop:
            logger.warning(f"No shop found for user {current_user.id}")
            return []

        logger.info(f"Fetching orders for shop {shop.id} owned by {current_user.id}")

        # Build query - get all orders for this shop
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
            # Join with customer info for search
            from sqlalchemy import or_
            query = query.join(User, Order.customer_id == User.id).filter(
                or_(
                    Order.id.contains(search),
                    User.first_name.contains(search),
                    User.last_name.contains(search),
                    User.email.contains(search)
                )
            )

        # Pagination
        offset = (page - 1) * limit
        orders = query.order_by(Order.created_at.desc()).offset(offset).limit(limit).all()

        logger.info(f"Found {len(orders)} orders for shop {shop.id}")

        # Transform to response format
        result = []
        for order in orders:
            customer = db.query(User).filter(User.id == order.customer_id).first()
            order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()

            items_response = []
            for item in order_items:
                # Check both product_id and casual_listing_id
                product = None
                casual_listing = None

                if item.product_id:
                    product = db.query(Product).filter(Product.id == item.product_id).first()
                elif item.casual_listing_id:
                    casual_listing = db.query(CasualListing).filter(CasualListing.id == item.casual_listing_id).first()

                # Get product details based on type
                if casual_listing:
                    unified_product_id = item.casual_listing_id
                    product_type = "casual"
                    product_name = casual_listing.title
                    product_image = casual_listing.image_urls[0] if casual_listing.image_urls else None
                elif product:
                    unified_product_id = item.product_id
                    product_type = "regular"
                    product_name = product.name
                    product_image = product.image_urls[0] if product.image_urls and len(product.image_urls) > 0 else None
                else:
                    unified_product_id = item.product_id or item.casual_listing_id or "unknown"
                    product_type = "unknown"
                    product_name = "Product No Longer Available"
                    product_image = None

                items_response.append(OrderItemResponse(
                    id=item.id,
                    product_id=unified_product_id,
                    product_type=product_type,
                    product_name=product_name,
                    product_image=product_image,
                    quantity=item.quantity,
                    unit_price=float(item.unit_price),
                    total_price=float(item.total_price),
                    shop_id=shop.id,
                    shop_name=shop.name
                ))

            result.append(VendorOrderResponse(
                id=order.id,
                shop_id=shop.id,
                shop_name=shop.name,
                shop_owner_id=shop.owner_id,
                customer_id=order.customer_id,
                customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
                customer_email=customer.email if customer else "unknown@email.com",
                status=order.status.value,
                payment_status=order.payment_status.value,
                total_amount=float(order.total_amount),
                shipping_address=order.shipping_address or "No address provided",
                tracking_number=order.tracking_number,
                created_at=order.created_at.isoformat(),
                updated_at=order.updated_at.isoformat(),
                items=items_response,
                item_count=len(items_response)
            ))

        logger.info(f"Successfully transformed {len(result)} orders for response")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shop owner orders: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve orders"
        )

@router.get("/customer/orders", response_model=CustomerOrdersResponse)
def get_customer_orders_optimized(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get orders for the current customer - optimized version with full order details"""
    try:
        logger.info(f"Fetching orders for customer {current_user.id}")

        # Build base query for customer orders
        query = db.query(Order).filter(Order.customer_id == current_user.id)

        # Apply status filter if provided
        if status:
            try:
                order_status = OrderStatus(status)
                query = query.filter(Order.status == order_status)
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid order status: {status}"
                )

        # Pagination
        offset = (page - 1) * limit
        orders = query.order_by(Order.created_at.desc()).offset(offset).limit(limit).all()

        logger.info(f"Found {len(orders)} orders for customer {current_user.id}")

        # Get customer info
        customer = db.query(User).filter(User.id == current_user.id).first()

        # Transform orders to response format
        result = []
        for order in orders:
            # Get order items
            order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()

            # Determine if this is a single or multi-vendor order
            # Orders with shop_id OR orders with NULL shop_id (casual marketplace) are treated as single-vendor
            # Multi-vendor orders are identified by having notes with "multi-vendor master order"
            is_multi_vendor = order.notes and "multi-vendor master order" in order.notes.lower()

            if not is_multi_vendor:
                # Single vendor order (including casual marketplace orders with NULL shop_id)
                shop = db.query(Shop).filter(Shop.id == order.shop_id).first() if order.shop_id else None

                items_response = []
                for item in order_items:
                    # Check both product_id and casual_listing_id
                    product = None
                    casual_listing = None

                    # Initialize with fallback values to prevent None errors
                    unified_product_id = "unknown"
                    product_type = "unknown"
                    product_name = "Product No Longer Available"
                    product_image = None
                    item_shop_name = "Unknown Shop"

                    if item.product_id:
                        product = db.query(Product).filter(Product.id == item.product_id).first()
                    if item.casual_listing_id:
                        casual_listing = db.query(CasualListing).filter(CasualListing.id == item.casual_listing_id).first()

                    # Get product details based on type - Industry standard polymorphic pattern
                    if casual_listing:
                        # Casual marketplace item
                        unified_product_id = item.casual_listing_id
                        product_type = "casual"
                        product_name = casual_listing.title
                        product_image = casual_listing.image_urls[0] if casual_listing.image_urls else None
                        item_shop_name = "Casual Marketplace"
                    elif product:
                        # Regular product from shop
                        unified_product_id = item.product_id
                        product_type = "regular"
                        product_name = product.name
                        product_image = product.image_urls[0] if product.image_urls and len(product.image_urls) > 0 else None
                        item_shop_name = shop.name if shop else "Unknown Shop"
                    else:
                        # Fallback for orphaned items (product deleted)
                        unified_product_id = item.product_id or item.casual_listing_id or "unknown"

                    items_response.append(OrderItemResponse(
                        id=item.id,
                        product_id=unified_product_id,
                        product_type=product_type,
                        product_name=product_name,
                        product_image=product_image,
                        quantity=item.quantity,
                        unit_price=float(item.unit_price),
                        total_price=float(item.total_price),
                        shop_id=shop.id if shop else None,
                        shop_name=item_shop_name
                    ))

                # Determine order-level shop name
                if not shop and any(item.casual_listing_id for item in order_items):
                    order_shop_name = "Casual Marketplace"
                elif shop:
                    order_shop_name = shop.name
                else:
                    order_shop_name = "Unknown Shop"

                result.append(OptimizedOrderResponse(
                    order_id=order.id,
                    customer_id=order.customer_id,
                    customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
                    customer_email=customer.email if customer else "unknown@email.com",
                    total_amount=float(order.total_amount),
                    status=order.status.value,
                    payment_status=order.payment_status.value,
                    shipping_address=order.shipping_address or "No address provided",
                    created_at=order.created_at.isoformat(),
                    order_type="single_vendor",
                    shop_id=order.shop_id,
                    shop_name=order_shop_name,
                    items=items_response
                ))
            else:
                # Multi-vendor master order - find related vendor orders
                vendor_orders = db.query(Order).filter(
                    Order.customer_id == current_user.id,
                    Order.notes.contains(f"Part of multi-vendor order {order.id}")
                ).all()

                vendor_orders_response = []
                total_items = 0

                for vendor_order in vendor_orders:
                    shop = db.query(Shop).filter(Shop.id == vendor_order.shop_id).first()
                    vendor_items = db.query(OrderItem).filter(OrderItem.order_id == vendor_order.id).all()

                    items_response = []
                    for item in vendor_items:
                        # Check both product_id and casual_listing_id
                        product = None
                        casual_listing = None

                        # Initialize with fallback values to prevent None errors
                        unified_product_id = "unknown"
                        product_type = "unknown"
                        product_name = "Product No Longer Available"
                        product_image = None
                        item_shop_name = "Unknown Shop"

                        if item.product_id:
                            product = db.query(Product).filter(Product.id == item.product_id).first()
                        if item.casual_listing_id:
                            casual_listing = db.query(CasualListing).filter(CasualListing.id == item.casual_listing_id).first()

                        # Get product details based on type - Industry standard polymorphic pattern
                        if casual_listing:
                            # Casual marketplace item
                            unified_product_id = item.casual_listing_id
                            product_type = "casual"
                            product_name = casual_listing.title
                            product_image = casual_listing.image_urls[0] if casual_listing.image_urls else None
                            item_shop_name = "Casual Marketplace"
                        elif product:
                            # Regular product from shop
                            unified_product_id = item.product_id
                            product_type = "regular"
                            product_name = product.name
                            product_image = product.image_urls[0] if product.image_urls and len(product.image_urls) > 0 else None
                            item_shop_name = shop.name if shop else "Unknown Shop"
                        else:
                            # Fallback for orphaned items
                            unified_product_id = item.product_id or item.casual_listing_id or "unknown"

                        items_response.append(OrderItemResponse(
                            id=item.id,
                            product_id=unified_product_id,
                            product_type=product_type,
                            product_name=product_name,
                            product_image=product_image,
                            quantity=item.quantity,
                            unit_price=float(item.unit_price),
                            total_price=float(item.total_price),
                            shop_id=shop.id if shop else None,
                            shop_name=item_shop_name
                        ))
                        total_items += item.quantity

                    vendor_orders_response.append(VendorOrderResponse(
                        id=vendor_order.id,
                        shop_id=vendor_order.shop_id,
                        shop_name=shop.name if shop else "Unknown Shop",
                        shop_owner_id=shop.owner_id if shop else "",
                        customer_id=vendor_order.customer_id,
                        customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
                        customer_email=customer.email if customer else "unknown@email.com",
                        status=vendor_order.status.value,
                        payment_status=vendor_order.payment_status.value,
                        total_amount=float(vendor_order.total_amount),
                        shipping_address=vendor_order.shipping_address or "No address provided",
                        tracking_number=vendor_order.tracking_number,
                        created_at=vendor_order.created_at.isoformat(),
                        updated_at=vendor_order.updated_at.isoformat(),
                        items=items_response,
                        item_count=len(items_response)
                    ))

                result.append(OptimizedOrderResponse(
                    order_id=order.id,
                    customer_id=order.customer_id,
                    customer_name=f"{customer.first_name} {customer.last_name}" if customer else "Unknown Customer",
                    customer_email=customer.email if customer else "unknown@email.com",
                    total_amount=float(order.total_amount),
                    status=order.status.value,
                    payment_status=order.payment_status.value,
                    shipping_address=order.shipping_address or "No address provided",
                    created_at=order.created_at.isoformat(),
                    order_type="multi_vendor",
                    vendor_orders=vendor_orders_response,
                    vendor_count=len(vendor_orders_response),
                    total_items=total_items
                ))

        # Calculate pagination info
        total_orders = db.query(Order).filter(Order.customer_id == current_user.id).count()
        total_pages = max(1, (total_orders + limit - 1) // limit)

        logger.info(f"Successfully transformed {len(result)} orders for customer response")
        return CustomerOrdersResponse(
            orders=result,
            total=total_orders,
            page=page,
            totalPages=total_pages
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting customer orders: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve customer orders"
        )
