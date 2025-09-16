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
    query = db.query(Product)

    if active_only:
        query = query.filter(Product.is_active == True)

    if category and category != 'all':
        query = query.filter(Product.category == category)

    if categories:
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

    return query.order_by(desc(Product.created_at)).offset(skip).limit(limit).all()

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
        
        # Transform to lightweight format
        lite_products = []
        for product in products:
            # Extract only the first image URL to save memory
            image_url = None
            image_count = 0
            has_video = False
            
            if product.image_urls:
                try:
                    import json
                    if isinstance(product.image_urls, str):
                        urls = json.loads(product.image_urls)
                    else:
                        urls = product.image_urls
                    
                    if urls and len(urls) > 0:
                        # Use placeholder for base64 images to save memory
                        first_url = urls[0]
                        if first_url.startswith('data:'):
                            image_url = '/api/placeholder/300/300'  # Use placeholder for base64
                        else:
                            image_url = first_url
                        image_count = len(urls)
                except:
                    image_url = '/api/placeholder/300/300'
                    image_count = 0
            
            if product.video_urls:
                try:
                    if isinstance(product.video_urls, str):
                        video_urls = json.loads(product.video_urls)
                    else:
                        video_urls = product.video_urls
                    has_video = bool(video_urls and len(video_urls) > 0)
                except:
                    has_video = False
            
            lite_product = {
                'id': product.id,
                'seller_id': product.seller_id,
                'name': product.name,
                'description': product.description,
                'price': product.price,
                'stock_quantity': product.stock_quantity,
                'category': product.category,
                'is_active': product.is_active,
                'image_url': image_url,
                'image_count': image_count,
                'has_video': has_video,
                'created_at': product.created_at,
                'updated_at': product.updated_at
            }
            lite_products.append(lite_product)
        
        # Get total count for pagination
        count_query = db.query(Product)
        if active_only:
            count_query = count_query.filter(Product.is_active == True)
        if category and category != 'all':
            count_query = count_query.filter(Product.category == category)
        if categories:
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
        
        return {
            'products': lite_products,
            'total_count': total_count,
            'page': (skip // limit) + 1,
            'per_page': limit,
            'has_more': has_more
        }
        
    except Exception as e:
        logger.error(f"Error getting products for catalog: {str(e)}")
        return {
            'products': [],
            'total_count': 0,
            'page': 1,
            'per_page': limit,
            'has_more': False
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

    if categories:
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
