from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime
import logging
import uuid

from models.shop import Shop
from models.user import User, UserRole
from schemas.shop import ShopCreate, ShopUpdate

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_shop(db: Session, shop_data: ShopCreate, owner_id: str) -> Shop:
    """Create a new shop with comprehensive validation."""
    try:
        # Verify the owner exists and is a shop owner
        owner = db.query(User).filter(User.id == owner_id).first()
        if not owner:
            logger.warning(f"Attempt to create shop with non-existent owner: {owner_id}")
            raise ValueError("Owner not found")
        
        if owner.role != UserRole.SHOP_OWNER:
            logger.warning(f"Attempt to create shop by non-shop-owner: {owner_id}")
            raise ValueError("Only shop owners can create shops")
        
        # Check if owner already has a shop
        existing_shop = db.query(Shop).filter(Shop.owner_id == owner_id).first()
        if existing_shop:
            logger.warning(f"Attempt to create multiple shops by owner: {owner_id}")
            raise ValueError("Shop owner already has a shop")
        
        # Check if shop name is already taken
        name_exists = db.query(Shop).filter(Shop.name == shop_data.name).first()
        if name_exists:
            logger.warning(f"Attempt to create shop with existing name: {shop_data.name}")
            raise ValueError("Shop name already exists")
        
        # Create shop object
        db_shop = Shop(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            name=shop_data.name,
            description=shop_data.description,
            address=shop_data.address,
            phone=shop_data.phone,
            email=shop_data.email,
            is_active=True,
            is_verified=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Add to database
        db.add(db_shop)
        db.commit()
        db.refresh(db_shop)
        
        logger.info(f"Shop created successfully: {shop_data.name} by owner {owner_id}")
        return db_shop
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Database integrity error creating shop: {str(e)}")
        if "name" in str(e).lower():
            raise ValueError("Shop name already exists")
        elif "phone" in str(e).lower():
            raise ValueError("Phone number already in use")
        elif "email" in str(e).lower():
            raise ValueError("Email already in use")
        else:
            raise ValueError("Database constraint violation")
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating shop: {str(e)}")
        raise

def get_shop_by_id(db: Session, shop_id: str) -> Optional[Shop]:
    """Get a shop by ID with error handling."""
    try:
        return db.query(Shop).filter(Shop.id == shop_id).first()
    except Exception as e:
        logger.error(f"Error getting shop by ID {shop_id}: {str(e)}")
        return None

def get_shop_by_owner_id(db: Session, owner_id: str) -> Optional[Shop]:
    """Get a shop by owner ID with error handling."""
    try:
        return db.query(Shop).filter(Shop.owner_id == owner_id).first()
    except Exception as e:
        logger.error(f"Error getting shop by owner ID {owner_id}: {str(e)}")
        return None

def get_shop_by_name(db: Session, name: str) -> Optional[Shop]:
    """Get a shop by name with error handling."""
    try:
        return db.query(Shop).filter(Shop.name == name).first()
    except Exception as e:
        logger.error(f"Error getting shop by name {name}: {str(e)}")
        return None

def get_shops(db: Session, skip: int = 0, limit: int = 100) -> List[Shop]:
    """Get all shops with pagination."""
    try:
        return db.query(Shop).offset(skip).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting shops: {str(e)}")
        return []

def get_active_shops(db: Session, skip: int = 0, limit: int = 100) -> List[Shop]:
    """Get active shops with pagination."""
    try:
        return db.query(Shop).filter(Shop.is_active == True).offset(skip).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting active shops: {str(e)}")
        return []

def update_shop(db: Session, shop_id: str, shop_data: ShopUpdate) -> Optional[Shop]:
    """Update a shop with comprehensive validation."""
    try:
        # Get existing shop
        db_shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not db_shop:
            logger.warning(f"Attempt to update non-existent shop: {shop_id}")
            return None
        
        # Update fields if provided
        update_data = shop_data.dict(exclude_unset=True)
        
        # Check for name uniqueness if name is being updated
        if 'name' in update_data:
            existing_shop = db.query(Shop).filter(
                Shop.name == update_data['name'], 
                Shop.id != shop_id
            ).first()
            if existing_shop:
                logger.warning(f"Attempt to update shop with existing name: {update_data['name']}")
                raise ValueError("Shop name already exists")
        
        # Update shop attributes
        for field, value in update_data.items():
            setattr(db_shop, field, value)
        
        db_shop.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(db_shop)
        
        logger.info(f"Shop updated successfully: {shop_id}")
        return db_shop
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating shop {shop_id}: {str(e)}")
        raise

def delete_shop(db: Session, shop_id: str) -> bool:
    """Delete a shop (soft delete by setting is_active to False)."""
    try:
        db_shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not db_shop:
            logger.warning(f"Attempt to delete non-existent shop: {shop_id}")
            return False
        
        db_shop.is_active = False
        db_shop.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Shop deleted successfully: {shop_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting shop {shop_id}: {str(e)}")
        return False

def verify_shop(db: Session, shop_id: str) -> bool:
    """Verify a shop (admin function)."""
    try:
        db_shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not db_shop:
            logger.warning(f"Attempt to verify non-existent shop: {shop_id}")
            return False
        
        db_shop.is_verified = True
        db_shop.updated_at = datetime.utcnow()
        
        db.commit()
        
        logger.info(f"Shop verified successfully: {shop_id}")
        return True
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error verifying shop {shop_id}: {str(e)}")
        return False