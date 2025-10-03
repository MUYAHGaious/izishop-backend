from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
from models.product import Product, ProductReview
from models.user import User
from schemas.product import ProductCreate, ProductUpdate
from typing import List, Optional, Dict
import logging
from core.exceptions import ResourceNotFoundError, BusinessLogicError

logger = logging.getLogger(__name__)

def create_product(db: Session, product_data: ProductCreate, seller_id: str) -> Product:
    """Create a new product for a seller"""
    try:
        # Verify seller exists
        seller = db.query(User).filter(User.id == seller_id).first()
        if not seller:
            raise ValueError("Seller not found")
        
        # Create product
        product = Product(
            seller_id=seller_id,
            name=product_data.name,
            description=product_data.description,
            price=product_data.price,
            stock_quantity=product_data.stock_quantity,
            category=product_data.category,
            # Enhanced product fields
            sku=product_data.sku,
            brand=product_data.brand,
            condition=product_data.condition,
            # Product specifications
            weight=product_data.weight,
            dimensions=product_data.dimensions,
            specifications=product_data.specifications,
            materials=product_data.materials,
            manufacturing_location=product_data.manufacturing_location,
            is_active=product_data.is_active,
            image_urls=product_data.image_urls if hasattr(product_data, 'image_urls') else None,
            video_urls=product_data.video_urls if hasattr(product_data, 'video_urls') else None
        )
        
        db.add(product)
        db.commit()
        db.refresh(product)
        
        logger.info(f"Product created: {product.name} by seller {seller_id}")
        return product
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating product: {str(e)}")
        raise

def get_product_by_id(db: Session, product_id: str) -> Optional[Product]:
    """Get a product by ID"""
    return db.query(Product).filter(Product.id == product_id).first()

def get_products_by_seller(db: Session, seller_id: str, skip: int = 0, limit: int = 100, active_only: bool = False) -> List[Product]:
    """Get all products for a specific seller"""
    query = db.query(Product).filter(Product.seller_id == seller_id)
    
    if active_only:
        query = query.filter(Product.is_active == True)
    
    return query.offset(skip).limit(limit).all()

def get_all_products(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    category: Optional[str] = None,
    categories: Optional[List[str]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[int] = None,
) -> List[Product]:
    """Get all products (for product catalog) with optional filters"""
    logger.info(f"🔍 get_all_products called with filters: skip={skip}, limit={limit}, active_only={active_only}, category={category}, categories={categories}, min_price={min_price}, max_price={max_price}, min_rating={min_rating}")

    query = db.query(Product)

    if active_only:
        query = query.filter(Product.is_active == True)

    if category and category != 'all':
        query = query.filter(Product.category == category)

    if categories and categories is not None:
        # Normalize and filter non-empty strings
        cats = [c for c in categories if isinstance(c, str) and c]
        if cats:
            query = query.filter(Product.category.in_(cats))

    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if min_rating is not None:
        avg_subq = (
            db.query(
                ProductReview.product_id.label('pid'),
                func.avg(ProductReview.rating).label('avg_rating')
            )
            .filter(ProductReview.is_active == True)
            .group_by(ProductReview.product_id)
            .subquery()
        )
        query = query.join(avg_subq, Product.id == avg_subq.c.pid)
        query = query.filter(avg_subq.c.avg_rating >= min_rating)

    # Execute query and log results
    products = query.order_by(desc(Product.created_at)).offset(skip).limit(limit).all()

    # Enhanced logging for debugging
    logger.info(f"📊 Database query executed successfully. Found {len(products)} products")

    if products:
        sample_product = products[0]
        logger.info(f"📝 Sample product data: id={sample_product.id}, name={sample_product.name}, seller_id={sample_product.seller_id}, is_active={sample_product.is_active}, image_urls_type={type(sample_product.image_urls)}, image_urls_length={len(sample_product.image_urls) if sample_product.image_urls else 0}")

        # Log image URL details for debugging
        if sample_product.image_urls:
            try:
                import json
                if isinstance(sample_product.image_urls, str):
                    parsed_urls = json.loads(sample_product.image_urls)
                    logger.info(f"🖼️ Sample product image URLs (parsed from JSON): {parsed_urls[:2] if len(parsed_urls) > 2 else parsed_urls}")
                else:
                    logger.info(f"🖼️ Sample product image URLs (direct): {sample_product.image_urls[:2] if len(sample_product.image_urls) > 2 else sample_product.image_urls}")
            except Exception as e:
                logger.warning(f"⚠️ Could not parse image URLs for sample product: {e}")
    else:
        logger.warning(f"⚠️ No products found with the given filters")

        # Additional debugging: Check total products in database
        total_products_in_db = db.query(Product).count()
        active_products_in_db = db.query(Product).filter(Product.is_active == True).count()
        logger.info(f"📈 Database totals: {total_products_in_db} total products, {active_products_in_db} active products")

    return products

def get_products_for_catalog(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    category: Optional[str] = None,
    categories: Optional[List[str]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[int] = None,
) -> dict:
    """
    Memory-efficient product retrieval for catalog display
    Returns products with minimal data to prevent browser memory issues
    """
    logger.info(f"🛒 get_products_for_catalog called with params: skip={skip}, limit={limit}, active_only={active_only}, category={category}, categories={categories}")

    try:
        # Get products without loading large image data
        products = get_all_products(
            db,
            skip,
            limit,
            active_only,
            category,
            categories,
            min_price,
            max_price,
            min_rating,
        )

        logger.info(f"📦 Retrieved {len(products)} raw products from get_all_products()")
        
        # Transform to lightweight format
        lite_products = []
        transformation_errors = []

        for i, product in enumerate(products):
            try:
                logger.info(f"🔄 Processing product {i+1}/{len(products)}: id={product.id}, name={product.name}")

                # Extract only the first image URL to save memory
                image_url = None
                image_count = 0
                has_video = False

                if product.image_urls:
                    try:
                        import json
                        logger.info(f"🖼️ Raw image_urls for product {product.id}: type={type(product.image_urls)}, value={str(product.image_urls)[:200]}...")

                        if isinstance(product.image_urls, str):
                            urls = json.loads(product.image_urls)
                            logger.info(f"📜 Parsed URLs from JSON string: {urls}")
                        else:
                            urls = product.image_urls
                            logger.info(f"📜 Direct URLs (not JSON): {urls}")

                        if urls and len(urls) > 0:
                            # Handle base64 images by creating a proper endpoint URL
                            first_url = urls[0]
                            logger.info(f"🎯 First URL: {first_url[:100]}...")

                            if first_url.startswith('data:'):
                                # Create a proper image endpoint URL for base64 images
                                image_url = f'/api/products/{product.id}/image/0'
                                logger.info(f"🔗 Created endpoint URL for base64: {image_url}")
                            else:
                                image_url = first_url
                                logger.info(f"🔗 Using direct URL: {image_url}")
                            image_count = len(urls)
                        else:
                            logger.warning(f"⚠️ Empty or null URLs array for product {product.id}")
                            image_url = '/api/placeholder/300/300'
                            image_count = 0

                    except json.JSONDecodeError as e:
                        logger.error(f"❌ JSON decode error for product {product.id} image_urls: {e}")
                        image_url = '/api/placeholder/300/300'
                        image_count = 0
                        transformation_errors.append(f"JSON decode error for product {product.id}: {e}")
                    except Exception as e:
                        logger.error(f"❌ Unexpected error processing image URLs for product {product.id}: {e}", exc_info=True)
                        image_url = '/api/placeholder/300/300'
                        image_count = 0
                        transformation_errors.append(f"Image processing error for product {product.id}: {e}")
                else:
                    logger.info(f"ℹ️ No image_urls for product {product.id}")
                    image_url = '/api/placeholder/300/300'
                    image_count = 0

                # Process video URLs
                if product.video_urls:
                    try:
                        if isinstance(product.video_urls, str):
                            video_urls = json.loads(product.video_urls)
                        else:
                            video_urls = product.video_urls
                        has_video = bool(video_urls and len(video_urls) > 0)
                    except:
                        has_video = False
            
                # Get shop information for this product
                shop_info = {}
                if product.seller_id:
                    try:
                        from models.shop import Shop
                        logger.info(f"🏪 Fetching shop info for seller_id: {product.seller_id}")

                        # Only select the basic columns that exist in the database
                        shop = db.query(
                            Shop.id,
                            Shop.owner_id,  # IMPORTANT: Need this for messaging!
                            Shop.name,
                            Shop.is_verified,
                            Shop.average_rating,
                            Shop.total_reviews,
                            Shop.address
                        ).filter(Shop.owner_id == product.seller_id).first()

                        if shop:
                            shop_info = {
                                'shop_id': shop.id,
                                'shop_owner_id': shop.owner_id,  # CRITICAL: This is the user ID to message!
                                'shop_name': shop.name,
                                'shop_verified': shop.is_verified,
                                'shop_rating': shop.average_rating,
                                'shop_reviews': shop.total_reviews,
                                'shop_location': shop.address or 'Cameroon'
                            }
                            logger.info(f"🏪 Shop info found: {shop_info}")
                        else:
                            logger.warning(f"⚠️ No shop found for seller_id: {product.seller_id}")

                    except Exception as e:
                        logger.error(f"❌ Failed to get shop info for product {product.id}, seller_id {product.seller_id}: {e}", exc_info=True)
                        transformation_errors.append(f"Shop info error for product {product.id}: {e}")
                else:
                    logger.warning(f"⚠️ No seller_id for product {product.id}")
            
                # Create lite product with comprehensive error handling
                try:
                    lite_product = {
                        'id': product.id,
                        'seller_id': product.seller_id,
                        'name': product.name,
                        'description': product.description,
                        'price': float(product.price) if product.price else 0.0,
                        'stock_quantity': product.stock_quantity or 0,
                        'category': product.category,
                        'is_active': product.is_active,
                        'image_url': image_url,
                        'image_count': image_count,
                        'has_video': has_video,
                        'created_at': product.created_at,
                        'updated_at': product.updated_at,
                        # Include shop information
                        **shop_info
                    }

                    # Validate the created lite product
                    required_fields = ['id', 'name', 'price']
                    for field in required_fields:
                        if lite_product.get(field) is None:
                            logger.warning(f"⚠️ Missing required field '{field}' for product {product.id}")

                    lite_products.append(lite_product)
                    logger.info(f"✅ Successfully transformed product {product.id} to lite format")

                except Exception as e:
                    logger.error(f"❌ Failed to create lite product for {product.id}: {e}", exc_info=True)
                    transformation_errors.append(f"Lite product creation error for {product.id}: {e}")
                    # Continue processing other products even if one fails

            except Exception as e:
                logger.error(f"❌ Unexpected error processing product at index {i}: {e}", exc_info=True)
                transformation_errors.append(f"Product processing error at index {i}: {e}")
                # Continue processing other products
        
        # Get total count for pagination
        count_query = db.query(Product)
        if active_only:
            count_query = count_query.filter(Product.is_active == True)
        if category and category != 'all':
            count_query = count_query.filter(Product.category == category)
        if categories and categories is not None:
            cats = [c for c in categories if isinstance(c, str) and c]
            if cats:
                count_query = count_query.filter(Product.category.in_(cats))
        if min_price is not None:
            count_query = count_query.filter(Product.price >= min_price)
        if max_price is not None:
            count_query = count_query.filter(Product.price <= max_price)
        if min_rating is not None:
            avg_subq = (
                db.query(
                    ProductReview.product_id.label('pid'),
                    func.avg(ProductReview.rating).label('avg_rating')
                )
                .filter(ProductReview.is_active == True)
                .group_by(ProductReview.product_id)
                .subquery()
            )
            count_query = count_query.join(avg_subq, Product.id == avg_subq.c.pid)
            count_query = count_query.filter(avg_subq.c.avg_rating >= min_rating)
        
        total_count = count_query.count()
        has_more = (skip + len(lite_products)) < total_count

        # Report any transformation errors that occurred
        if transformation_errors:
            logger.warning(f"⚠️ {len(transformation_errors)} transformation errors occurred:")
            for error in transformation_errors:
                logger.warning(f"  • {error}")

        # Final response logging
        logger.info(f"✅ get_products_for_catalog completed successfully:")
        logger.info(f"  📊 Processed {len(products)} raw products into {len(lite_products)} lite products")
        logger.info(f"  📈 Total count: {total_count}, Page: {(skip // limit) + 1}, Has more: {has_more}")

        # Log sample lite product for debugging
        if lite_products:
            sample_lite = lite_products[0]
            logger.info(f"  📝 Sample lite product: id={sample_lite.get('id', 'N/A')}, name={sample_lite.get('name', 'N/A')}, image_url={sample_lite.get('image_url', 'N/A')}, shop_name={sample_lite.get('shop_name', 'N/A')}")
        else:
            logger.error(f"❌ No lite products were created! This indicates a serious issue.")

        response = {
            'products': lite_products,
            'total_count': total_count,
            'page': (skip // limit) + 1,
            'per_page': limit,
            'has_more': has_more
        }

        # Add error information to response if there were issues
        if transformation_errors:
            response['_debug_errors'] = transformation_errors

        return response
        
    except Exception as e:
        logger.error(f"❌ Critical error in get_products_for_catalog: {str(e)}", exc_info=True)

        # Try to get basic database information for debugging
        try:
            total_products_in_db = db.query(Product).count()
            logger.info(f"📊 Database debug info: {total_products_in_db} total products in database")
        except Exception as db_error:
            logger.error(f"❌ Cannot even access database: {db_error}")

        return {
            'products': [],
            'total_count': 0,
            'page': 1,
            'per_page': limit,
            'has_more': False,
            '_error': str(e)
        }

def search_products(
    db: Session,
    search_term: str,
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    categories: Optional[List[str]] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[int] = None,
) -> List[Product]:
    """Search products by name or description with optional filters"""
    query = db.query(Product).filter(
        and_(
            Product.is_active == True,
            or_(
                Product.name.ilike(f"%{search_term}%"),
                Product.description.ilike(f"%{search_term}%")
            )
        )
    )

    if category:
        query = query.filter(Product.category == category)

    if categories and categories is not None:
        cats = [c for c in categories if isinstance(c, str) and c]
        if cats:
            query = query.filter(Product.category.in_(cats))

    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)

    if min_rating is not None:
        avg_subq = (
            db.query(
                ProductReview.product_id.label('pid'),
                func.avg(ProductReview.rating).label('avg_rating')
            )
            .filter(ProductReview.is_active == True)
            .group_by(ProductReview.product_id)
            .subquery()
        )
        query = query.join(avg_subq, Product.id == avg_subq.c.pid)
        query = query.filter(avg_subq.c.avg_rating >= min_rating)

    return query.order_by(desc(Product.created_at)).offset(skip).limit(limit).all()

def update_product(db: Session, product_id: str, product_data: ProductUpdate, seller_id: str) -> Optional[Product]:
    """Update a product (only by the seller)"""
    try:
        product = db.query(Product).filter(
            and_(Product.id == product_id, Product.seller_id == seller_id)
        ).first()
        
        if not product:
            return None
        
        # Update fields
        for field, value in product_data.dict(exclude_unset=True).items():
            setattr(product, field, value)
        
        db.commit()
        db.refresh(product)
        
        logger.info(f"Product updated: {product.name} by seller {seller_id}")
        return product
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating product: {str(e)}")
        raise

def delete_product(db: Session, product_id: str, seller_id: str) -> bool:
    """Delete a product (soft delete - mark as inactive)"""
    try:
        product = db.query(Product).filter(
            and_(Product.id == product_id, Product.seller_id == seller_id)
        ).first()
        
        if not product:
            return False
        
        # Soft delete
        product.is_active = False
        db.commit()
        
        logger.info(f"Product deleted: {product.name} by seller {seller_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting product: {str(e)}")
        raise

def get_seller_product_stats(db: Session, seller_id: str) -> dict:
    """Get product statistics for a seller"""
    total_products = db.query(Product).filter(Product.seller_id == seller_id).count()
    active_products = db.query(Product).filter(
        and_(Product.seller_id == seller_id, Product.is_active == True)
    ).count()
    
    low_stock_products = db.query(Product).filter(
        and_(
            Product.seller_id == seller_id,
            Product.is_active == True,
            Product.stock_quantity < 10
        )
    ).count()
    
    out_of_stock_products = db.query(Product).filter(
        and_(
            Product.seller_id == seller_id,
            Product.is_active == True,
            Product.stock_quantity == 0
        )
    ).count()
    
    return {
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": total_products - active_products,
        "low_stock_products": low_stock_products,
        "out_of_stock_products": out_of_stock_products
    }

def update_product_stock(db: Session, product_id: str, quantity_change: int, seller_id: str) -> Optional[Product]:
    """Update product stock quantity"""
    try:
        product = db.query(Product).filter(
            and_(Product.id == product_id, Product.seller_id == seller_id)
        ).first()
        
        if not product:
            return None
        
        new_quantity = product.stock_quantity + quantity_change
        if new_quantity < 0:
            raise ValueError("Stock quantity cannot be negative")
        
        product.stock_quantity = new_quantity
        db.commit()
        db.refresh(product)
        
        logger.info(f"Product stock updated: {product.name} - {quantity_change} units")
        return product
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating product stock: {str(e)}")
        raise

# Product Review Services
def create_product_review(
    db: Session, 
    product_id: str, 
    user_id: str, 
    review_data: dict
) -> ProductReview:
    """Create a new product review"""
    try:
        # Check if product exists
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ResourceNotFoundError(f"Product with id {product_id} not found")
        
        # Check if user already reviewed this product
        existing_review = db.query(ProductReview).filter(
            and_(
                ProductReview.product_id == product_id,
                ProductReview.user_id == user_id
            )
        ).first()
        
        if existing_review:
            raise BusinessLogicError("You have already reviewed this product")
        
        # Create review
        review = ProductReview(
            product_id=product_id,
            user_id=user_id,
            rating=review_data["rating"],
            title=review_data.get("title"),
            content=review_data.get("content"),
            is_verified_purchase=review_data.get("is_verified_purchase", False)
        )
        
        db.add(review)
        db.commit()
        db.refresh(review)
        
        # Update product rating
        update_product_rating(db, product_id)
        
        return review
        
    except Exception as e:
        db.rollback()
        raise e

def get_product_reviews(
    db: Session, 
    product_id: str, 
    skip: int = 0, 
    limit: int = 10,
    sort_by: str = "newest"
) -> List[ProductReview]:
    """Get reviews for a product with pagination and sorting"""
    try:
        query = db.query(ProductReview).filter(
            and_(
                ProductReview.product_id == product_id,
                ProductReview.is_active == True
            )
        )
        
        # Apply sorting
        if sort_by == "newest":
            query = query.order_by(ProductReview.created_at.desc())
        elif sort_by == "oldest":
            query = query.order_by(ProductReview.created_at.asc())
        elif sort_by == "highest":
            query = query.order_by(ProductReview.rating.desc())
        elif sort_by == "lowest":
            query = query.order_by(ProductReview.rating.asc())
        elif sort_by == "helpful":
            query = query.order_by(ProductReview.helpful_count.desc())
        
        # Apply pagination
        reviews = query.offset(skip).limit(limit).all()
        
        # Add user information
        for review in reviews:
            user = db.query(User).filter(User.id == review.user_id).first()
            if user:
                review.user_name = f"{user.first_name} {user.last_name}"
                review.user_avatar = None  # TODO: Add user avatar field
        
        return reviews
        
    except Exception as e:
        logging.error(f"Error getting product reviews: {str(e)}")
        raise e

def get_product_review_stats(db: Session, product_id: str) -> Dict:
    """Get review statistics for a product"""
    try:
        # Get average rating and total reviews
        result = db.query(
            func.avg(ProductReview.rating).label('average'),
            func.count(ProductReview.id).label('total')
        ).filter(
            and_(
                ProductReview.product_id == product_id,
                ProductReview.is_active == True
            )
        ).first()
        
        # Get rating distribution
        distribution_result = db.query(
            ProductReview.rating,
            func.count(ProductReview.id).label('count')
        ).filter(
            and_(
                ProductReview.product_id == product_id,
                ProductReview.is_active == True
            )
        ).group_by(ProductReview.rating).all()
        
        distribution = {i: 0 for i in range(1, 6)}
        for rating, count in distribution_result:
            distribution[rating] = count
        
        return {
            'average_rating': round(float(result.average), 1) if result.average else 0.0,
            'total_reviews': result.total or 0,
            'rating_distribution': distribution
        }
        
    except Exception as e:
        logging.error(f"Error getting product review stats: {str(e)}")
        raise e

def update_product_rating(db: Session, product_id: str):
    """Update product's average rating based on reviews"""
    try:
        stats = get_product_review_stats(db, product_id)
        product = db.query(Product).filter(Product.id == product_id).first()
        
        if product:
            # Update product rating (you may need to add this field to Product model)
            # product.rating = stats['average_rating']
            # product.review_count = stats['total_reviews']
            db.commit()
            
    except Exception as e:
        logging.error(f"Error updating product rating: {str(e)}")
        # Don't raise error as this is not critical

def get_related_products(
    db: Session, 
    product_id: str, 
    limit: int = 6
) -> List[Product]:
    """Get related products based on category and seller"""
    try:
        # Get current product
        current_product = db.query(Product).filter(Product.id == product_id).first()
        if not current_product:
            return []
        
        # Get products from same category and seller (excluding current product)
        related_products = db.query(Product).filter(
            and_(
                Product.id != product_id,
                Product.is_active == True,
                Product.seller_id == current_product.seller_id
            )
        ).limit(limit).all()
        
        # If not enough products from same seller, get from same category
        if len(related_products) < limit:
            remaining_limit = limit - len(related_products)
            category_products = db.query(Product).filter(
                and_(
                    Product.id != product_id,
                    Product.is_active == True,
                    Product.id.notin_([p.id for p in related_products])
                )
            ).limit(remaining_limit).all()
            
            related_products.extend(category_products)
        
        return related_products
        
    except Exception as e:
        logging.error(f"Error getting related products: {str(e)}")
        return []
