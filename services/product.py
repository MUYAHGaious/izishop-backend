from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc
from models.product import Product
from models.user import User
from schemas.product import ProductCreate, ProductUpdate
from typing import List, Optional
import logging

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

def get_all_products(db: Session, skip: int = 0, limit: int = 100, active_only: bool = True) -> List[Product]:
    """Get all products (for product catalog)"""
    query = db.query(Product)
    
    if active_only:
        query = query.filter(Product.is_active == True)
    
    return query.order_by(desc(Product.created_at)).offset(skip).limit(limit).all()

def search_products(db: Session, search_term: str, skip: int = 0, limit: int = 100) -> List[Product]:
    """Search products by name or description"""
    query = db.query(Product).filter(
        and_(
            Product.is_active == True,
            or_(
                Product.name.ilike(f"%{search_term}%"),
                Product.description.ilike(f"%{search_term}%")
            )
        )
    )
    
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