import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Boolean, Float, func
from sqlalchemy.orm import relationship, Session
from database.base import Base

class Rating(Base):
    __tablename__ = "ratings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=False)
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review = Column(Text, nullable=True)
    is_verified_purchase = Column(Boolean, default=False)  # If user purchased from shop
    is_active = Column(Boolean, default=True)  # For moderation
    is_flagged = Column(Boolean, default=False)
    helpful_count = Column(Integer, default=0)  # Thumbs up count
    not_helpful_count = Column(Integer, default=0)  # Thumbs down count
    admin_notes = Column(Text, nullable=True)  # For moderation
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="ratings")
    shop = relationship("Shop", back_populates="ratings")
    helpfulness_votes = relationship("RatingHelpfulness", back_populates="rating", cascade="all, delete-orphan")
    flags = relationship("RatingFlag", back_populates="rating", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Rating(id={self.id}, user_id={self.user_id}, shop_id={self.shop_id}, rating={self.rating})>"

    @classmethod
    def get_shop_average_rating(cls, db: Session, shop_id: str):
        """Calculate average rating for a shop"""
        result = db.query(
            func.avg(cls.rating).label('average'),
            func.count(cls.id).label('total_reviews')
        ).filter(
            cls.shop_id == shop_id,
            cls.is_active == True
        ).first()
        
        return {
            'average_rating': round(float(result.average), 1) if result.average else 0.0,
            'total_reviews': result.total_reviews or 0
        }

    @classmethod
    def get_rating_distribution(cls, db: Session, shop_id: str):
        """Get rating distribution (how many 1-star, 2-star, etc.)"""
        result = db.query(
            cls.rating,
            func.count(cls.id).label('count')
        ).filter(
            cls.shop_id == shop_id,
            cls.is_active == True
        ).group_by(cls.rating).all()
        
        distribution = {i: 0 for i in range(1, 6)}
        for rating, count in result:
            distribution[rating] = count
            
        return distribution


class RatingHelpfulness(Base):
    __tablename__ = "rating_helpfulness"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    rating_id = Column(String, ForeignKey("ratings.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    is_helpful = Column(Boolean, nullable=False)  # True for helpful, False for not helpful
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    rating = relationship("Rating", back_populates="helpfulness_votes")
    user = relationship("User")

    def __repr__(self):
        return f"<RatingHelpfulness(rating_id={self.rating_id}, user_id={self.user_id}, is_helpful={self.is_helpful})>"


class RatingFlag(Base):
    __tablename__ = "rating_flags"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    rating_id = Column(String, ForeignKey("ratings.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    reason = Column(String, nullable=False)  # spam, inappropriate, fake, etc.
    description = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)
    admin_action = Column(String, nullable=True)  # approved, dismissed, warning_sent
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    rating = relationship("Rating", back_populates="flags")
    user = relationship("User")

    def __repr__(self):
        return f"<RatingFlag(rating_id={self.rating_id}, reason={self.reason})>"


class ShopStats(Base):
    __tablename__ = "shop_stats"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    shop_id = Column(String, ForeignKey("shops.id"), nullable=False, unique=True)
    average_rating = Column(Float, default=0.0)
    total_reviews = Column(Integer, default=0)
    total_orders = Column(Integer, default=0)
    total_products = Column(Integer, default=0)
    total_sales = Column(Float, default=0.0)
    response_rate = Column(Float, default=0.0)  # Percentage of inquiries responded to
    response_time_hours = Column(Float, default=0.0)  # Average response time
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    shop = relationship("Shop", back_populates="stats")

    def __repr__(self):
        return f"<ShopStats(shop_id={self.shop_id}, average_rating={self.average_rating})>"

    @classmethod
    def update_rating_stats(cls, db: Session, shop_id: str):
        """Update shop rating statistics"""
        rating_data = Rating.get_shop_average_rating(db, shop_id)
        
        # Get or create shop stats
        shop_stats = db.query(cls).filter(cls.shop_id == shop_id).first()
        if not shop_stats:
            shop_stats = cls(shop_id=shop_id)
            db.add(shop_stats)
        
        # Update rating stats
        shop_stats.average_rating = rating_data['average_rating']
        shop_stats.total_reviews = rating_data['total_reviews']
        shop_stats.updated_at = datetime.utcnow()
        
        db.commit()
        return shop_stats