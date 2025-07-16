import uuid
from sqlalchemy import Column, String, Boolean, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database.base import Base

class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    image_url = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    # Relationships
    parent = relationship("Category", remote_side=[id], backref="children")
    products = relationship("Product", back_populates="category") 