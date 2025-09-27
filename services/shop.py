from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime
import logging
import uuid

from models.shop import Shop
from models.user import User, UserRole
from models.product import Product
from models.review import Review
from schemas.shop import ShopCreate, ShopUpdate
from schemas.review import ReviewResponse
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_shop(db: Session, shop_data: ShopCreate, owner_id: str) -> Shop:
    """Create a new shop with comprehensive validation."""
    try:
        logger.info("--- Entering create_shop service ---")
        # Verify the owner exists and is a shop owner
        logger.info(f"Step 1: Checking for owner with ID: {owner_id}")
        owner = db.query(User).filter(User.id == owner_id).first()
        if not owner:
            logger.warning(f"Attempt to create shop with non-existent owner: {owner_id}")
            raise ValueError("Owner not found")
        logger.info("Step 1 PASSED: Owner found.")
        
        logger.info(f"Step 2: Checking owner role. Role is: {owner.role}")
        if owner.role != UserRole.SHOP_OWNER:
            logger.warning(f"Attempt to create shop by non-shop-owner: {owner_id}")
            raise ValueError("Only shop owners can create shops")
        logger.info("Step 2 PASSED: Owner role is correct.")

        # Check if owner already has a shop
        logger.info(f"Step 3: Checking if owner {owner_id} already has a shop.")
        existing_shop = db.query(Shop).filter(Shop.owner_id == owner_id).first()
        if existing_shop:
            logger.warning(f"Attempt to create multiple shops by owner: {owner_id}")
            raise ValueError("Shop owner already has a shop")
        logger.info("Step 3 PASSED: Owner does not have a shop yet.")

        # Check if shop name is already taken
        logger.info(f"Step 4: Checking if shop name '{shop_data.name}' is taken.")
        name_exists = db.query(Shop).filter(Shop.name == shop_data.name).first()
        if name_exists:
            logger.warning(f"Attempt to create shop with existing name: {shop_data.name}")
            # Suggest alternative names
            suggested_names = []
            for i in range(1, 4):
                suggestion = f"{shop_data.name} ({i})"
                if not db.query(Shop).filter(Shop.name == suggestion).first():
                    suggested_names.append(suggestion)
            
            suggestion_text = f" Try: {', '.join(suggested_names[:2])}" if suggested_names else ""
            raise ValueError(f"Shop name '{shop_data.name}' is already taken.{suggestion_text}")
        logger.info("Step 4 PASSED: Shop name is available.")

        # Create shop object
        logger.info("Step 5: Creating Shop database object.")
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
        logger.info("Step 5 PASSED: Shop object created.")
        
        # Add to database
        logger.info("Step 6: Adding shop to session and committing.")
        db.add(db_shop)
        
        # Commit to database
        db.commit()
        
        db.refresh(db_shop)
        logger.info("Step 6 PASSED: Commit and refresh successful.")
        
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

def get_shops_by_owner_id(db: Session, owner_id: str) -> List[Shop]:
    """Get all shops by owner ID (supports multiple shops per owner)."""
    try:
        return db.query(Shop).filter(Shop.owner_id == owner_id).all()
    except Exception as e:
        logger.error(f"Error getting shops by owner ID {owner_id}: {str(e)}")
        return []

def get_shop_by_name(db: Session, name: str) -> Optional[Shop]:
    """Get a shop by name with error handling."""
    try:
        return db.query(Shop).filter(Shop.name == name).first()
    except Exception as e:
        logger.error(f"Error getting shop by name {name}: {str(e)}")
        return None

def get_shop_by_phone(db: Session, phone: str) -> Optional[Shop]:
    """Get a shop by phone number with error handling."""
    try:
        # Clean phone number (remove all non-digit characters)
        import re
        clean_phone = re.sub(r'\D', '', phone)
        return db.query(Shop).filter(Shop.phone == clean_phone).first()
    except Exception as e:
        logger.error(f"Error getting shop by phone {phone}: {str(e)}")
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

def get_featured_shops(db: Session, limit: int = 10) -> List[Shop]:
    """Get featured shops based on rating and verification status."""
    try:
        return db.query(Shop).filter(
            Shop.is_active == True,
            Shop.is_verified == True
        ).order_by(
            Shop.average_rating.desc(),
            Shop.created_at.desc()
        ).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting featured shops: {str(e)}")
        return []

def get_shop_products(db: Session, shop_id: str, skip: int = 0, limit: int = 20) -> List[Product]:
    """Get products for a specific shop."""
    try:
        # Verify shop exists and get shop owner
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            logger.warning(f"Attempt to get products for non-existent shop: {shop_id}")
            return []
        
        # Get products by shop owner (seller_id = shop.owner_id)
        return db.query(Product).filter(
            Product.seller_id == shop.owner_id,
            Product.is_active == True
        ).order_by(
            Product.created_at.desc()
        ).offset(skip).limit(limit).all()
    except Exception as e:
        logger.error(f"Error getting products for shop {shop_id}: {str(e)}")
        return []

def get_shop_reviews(db: Session, shop_id: str, skip: int = 0, limit: int = 20) -> List[ReviewResponse]:
    """Get reviews for a specific shop with user information."""
    try:
        # Verify shop exists
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            logger.warning(f"Attempt to get reviews for non-existent shop: {shop_id}")
            return []
        
        # Get real reviews with user information
        reviews = db.query(Review).join(User).filter(Review.shop_id == shop_id).offset(skip).limit(limit).all()
        
        # Convert to response format with user information
        review_responses = []
        for review in reviews:
            review_data = ReviewResponse.from_orm(review)
            review_data.user_name = f"{review.user.first_name} {review.user.last_name}".strip() or "Anonymous"
            review_data.user_avatar = review.user.profile_image_url
            review_responses.append(review_data)
        
        logger.info(f"Retrieved {len(review_responses)} real reviews for shop {shop_id}")
        return review_responses
    except Exception as e:
        logger.error(f"Error getting reviews for shop {shop_id}: {str(e)}")
        return []

def get_shop_about_data(db: Session, shop_id: str) -> dict:
    """Get comprehensive about data for a shop."""
    try:
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            return {}
        
        # Calculate real statistics
        product_count = db.query(Product).filter(Product.shop_id == shop_id).count()
        reviews = db.query(Review).filter(Review.shop_id == shop_id).all()
        total_reviews = len(reviews)
        average_rating = sum(review.rating for review in reviews) / total_reviews if total_reviews > 0 else 0.0
        
        # Parse JSON fields safely
        def safe_json_parse(json_str, default=None):
            if not json_str:
                return default
            try:
                return json.loads(json_str)
            except:
                return default
        
        about_data = {
            "id": shop.id,
            "name": shop.name,
            "description": shop.description,
            "mission": shop.mission,
            "vision": shop.vision,
            "website": shop.website,
            "address": shop.address,
            "phone": shop.phone,
            "email": shop.email,
            "profile_photo": shop.profile_photo,
            "background_image": shop.background_image,
            "is_active": shop.is_active,
            "is_verified": shop.is_verified,
            "created_at": shop.created_at,
            "updated_at": shop.updated_at,
            "average_rating": round(average_rating, 1),
            "total_reviews": total_reviews,
            "product_count": product_count,
            "followers_count": shop.followers_count or 0,
            "total_sales": shop.total_sales or 0.0,
            "business_hours": safe_json_parse(shop.business_hours, {}),
            "policies": safe_json_parse(shop.policies, {}),
            "team_members": safe_json_parse(shop.team_members, []),
            "milestones": safe_json_parse(shop.milestones, []),
            "certifications": safe_json_parse(shop.certifications, []),
            "coordinates": safe_json_parse(shop.coordinates, {}),
        }
        
        return about_data
    except Exception as e:
        logger.error(f"Error getting about data for shop {shop_id}: {str(e)}")
        return {}

def update_shop_statistics(db: Session, shop_id: str):
    """Update shop statistics based on current data."""
    try:
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop:
            return
        
        # Calculate and update statistics
        product_count = db.query(Product).filter(Product.shop_id == shop_id).count()
        reviews = db.query(Review).filter(Review.shop_id == shop_id).all()
        total_reviews = len(reviews)
        average_rating = sum(review.rating for review in reviews) / total_reviews if total_reviews > 0 else 0.0
        
        # Update shop with calculated values
        shop.product_count = product_count
        shop.total_reviews = total_reviews
        shop.average_rating = round(average_rating, 1)
        shop.updated_at = datetime.utcnow()
        
        db.commit()
        logger.info(f"Updated statistics for shop {shop_id}: {product_count} products, {total_reviews} reviews, {average_rating} rating")
        
    except Exception as e:
        logger.error(f"Error updating shop statistics for {shop_id}: {str(e)}")
        db.rollback()