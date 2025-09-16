import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, JSON
from sqlalchemy.orm import relationship
from database.base import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Hierarchical category support
    parent_category_id = Column(String, ForeignKey("categories.id"), nullable=True, index=True)
    category_level = Column(Integer, default=0)  # 0=root, 1=subcategory, etc.
    category_path = Column(String, nullable=True, index=True)  # For efficient queries
    sort_order = Column(Integer, default=0)  # For custom ordering

    # Category-specific fields
    required_fields = Column(JSON, nullable=True)  # Required fields for this category
    specifications_template = Column(JSON, nullable=True)  # Default specs template
    icon = Column(String, nullable=True)  # Category icon

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent = relationship("Category", remote_side=[id], back_populates="children")
    children = relationship("Category", back_populates="parent", cascade="all, delete-orphan") 