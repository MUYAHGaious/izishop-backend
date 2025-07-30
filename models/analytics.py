from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, JSON, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class TimeGranularity(enum.Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"

class MetricType(enum.Enum):
    REVENUE = "revenue"
    ORDERS = "orders"
    USERS = "users"
    SESSIONS = "sessions"
    CONVERSION = "conversion"
    AOV = "average_order_value"

class AnalyticsMetric(Base):
    """
    Time-series analytics data for real-time charts
    Optimized for fast querying and aggregation
    """
    __tablename__ = "analytics_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    date_key = Column(String(10), index=True)  # YYYY-MM-DD for daily aggregation
    hour_key = Column(String(13), index=True)  # YYYY-MM-DD-HH for hourly aggregation
    
    # Metric identification
    metric_type = Column(String(50), index=True)  # revenue, orders, users, etc.
    granularity = Column(String(20), index=True)  # hourly, daily, weekly, monthly
    
    # Dimensional data
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True, index=True)
    category_id = Column(Integer, nullable=True, index=True)
    region = Column(String(100), nullable=True, index=True)
    user_role = Column(String(50), nullable=True, index=True)
    
    # Metric values
    value = Column(Float, default=0.0)
    count = Column(Integer, default=0)
    
    # Additional metadata
    metadata = Column(JSON, nullable=True)
    
    # Audit fields
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    shop = relationship("Shop", back_populates="analytics_metrics", lazy="select")
    
    # Composite indexes for performance
    __table_args__ = (
        Index('idx_analytics_time_metric', 'timestamp', 'metric_type'),
        Index('idx_analytics_date_metric', 'date_key', 'metric_type'),
        Index('idx_analytics_hour_metric', 'hour_key', 'metric_type'),
        Index('idx_analytics_shop_time', 'shop_id', 'timestamp'),
        Index('idx_analytics_region_time', 'region', 'timestamp'),
        Index('idx_analytics_category_time', 'category_id', 'timestamp'),
    )

class RealtimeEvent(Base):
    """
    Stream of real-time events for immediate chart updates
    """
    __tablename__ = "realtime_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(100), unique=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Event data
    event_type = Column(String(50), index=True)  # order_created, payment_completed, user_registered
    entity_type = Column(String(50), index=True)  # order, user, shop, product
    entity_id = Column(Integer, index=True)
    
    # Event payload
    data = Column(JSON)
    
    # Processing status
    processed = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime, nullable=True)
    
    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)

class MLForecast(Base):
    """
    Machine learning forecasting results
    """
    __tablename__ = "ml_forecasts"
    
    id = Column(Integer, primary_key=True, index=True)
    forecast_id = Column(String(100), unique=True, index=True)
    
    # Forecast metadata
    metric_type = Column(String(50), index=True)
    forecast_date = Column(DateTime, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Forecast data
    predicted_value = Column(Float)
    confidence_lower = Column(Float)
    confidence_upper = Column(Float)
    confidence_level = Column(Float, default=0.95)
    
    # Model information
    model_name = Column(String(100))
    model_version = Column(String(50))
    
    # Dimensional filters
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True)
    category_id = Column(Integer, nullable=True)
    region = Column(String(100), nullable=True)
    
    # Additional metadata
    metadata = Column(JSON)

class AnomalyDetection(Base):
    """
    Anomaly detection results for real-time monitoring
    """
    __tablename__ = "anomaly_detections"
    
    id = Column(Integer, primary_key=True, index=True)
    detection_id = Column(String(100), unique=True, index=True)
    
    # Detection metadata
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    metric_type = Column(String(50), index=True)
    
    # Anomaly data
    actual_value = Column(Float)
    expected_value = Column(Float)
    anomaly_score = Column(Float)
    severity = Column(String(20), index=True)  # low, medium, high, critical
    
    # Detection algorithm
    algorithm = Column(String(100))
    threshold = Column(Float)
    
    # Dimensional context
    shop_id = Column(Integer, ForeignKey("shops.id"), nullable=True)
    category_id = Column(Integer, nullable=True)
    region = Column(String(100), nullable=True)
    
    # Resolution tracking
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    
    # Additional data
    metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

class AnalyticsAuditLog(Base):
    """
    Audit logging for analytics access and operations
    """
    __tablename__ = "analytics_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(String(100), unique=True, index=True)
    
    # Audit metadata
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    user_role = Column(String(50), index=True)
    
    # Action details
    action = Column(String(100), index=True)  # view_dashboard, export_data, modify_settings
    resource = Column(String(100), index=True)  # chart, report, forecast
    resource_id = Column(String(100), nullable=True)
    
    # Request details
    ip_address = Column(String(45))
    user_agent = Column(Text)
    request_id = Column(String(100))
    
    # Filter context
    filters_applied = Column(JSON)
    time_range = Column(String(50))
    
    # Result
    status = Column(String(20))  # success, failed, unauthorized
    error_message = Column(Text, nullable=True)
    
    # Additional metadata
    metadata = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", lazy="select")