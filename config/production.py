"""
Production configuration for IziShop Backend
"""
import os
from typing import Optional
from pydantic import BaseSettings, validator
from functools import lru_cache


class ProductionSettings(BaseSettings):
    """Production environment settings"""
    
    # Application settings
    app_name: str = "IziShop"
    app_version: str = "1.0.0"
    debug: bool = False
    testing: bool = False
    environment: str = "production"
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    
    # Database settings
    database_url: str
    db_pool_size: int = 20
    db_max_overflow: int = 30
    db_pool_timeout: int = 30
    db_pool_recycle: int = 3600
    db_echo: bool = False
    
    # Redis settings
    redis_url: str
    redis_pool_size: int = 10
    redis_timeout: int = 5
    
    # Security settings
    secret_key: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    bcrypt_rounds: int = 12
    
    # CORS settings
    allowed_origins: list = ["https://yourdomain.com"]
    allowed_methods: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allowed_headers: list = ["*"]
    allow_credentials: bool = True
    
    # Email settings
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    smtp_tls: bool = True
    email_from: str
    email_templates_dir: str = "/app/templates/email"
    
    # File storage settings
    upload_dir: str = "/app/uploads"
    max_file_size: int = 10485760  # 10MB
    allowed_file_types: list = ["jpg", "jpeg", "png", "gif", "pdf", "doc", "docx"]
    
    # AWS S3 settings (optional)
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    aws_bucket_name: Optional[str] = None
    aws_cloudfront_domain: Optional[str] = None
    
    # Tranzak settings
    tranzak_base_url: str
    tranzak_app_id: str
    tranzak_app_key: str
    tranzak_webhook_secret: str
    
    # Logging settings
    log_level: str = "INFO"
    log_file: str = "/app/logs/app.log"
    log_max_size: str = "100MB"
    log_backup_count: int = 5
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Monitoring settings
    sentry_dsn: Optional[str] = None
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_period: int = 3600
    
    # Background jobs
    celery_broker_url: str
    celery_result_backend: str
    
    # Performance settings
    gunicorn_workers: int = 4
    gunicorn_worker_class: str = "uvicorn.workers.UvicornWorker"
    gunicorn_max_requests: int = 1000
    gunicorn_max_requests_jitter: int = 50
    gunicorn_timeout: int = 30
    gunicorn_keepalive: int = 2
    
    # Health check settings
    health_check_enabled: bool = True
    health_check_interval: int = 60
    health_check_timeout: int = 10
    
    # Cache settings
    cache_default_timeout: int = 300
    cache_key_prefix: str = "izishop"
    
    # SSL settings
    ssl_redirect: bool = True
    secure_headers: bool = True
    
    # Third-party integrations
    google_maps_api_key: Optional[str] = None
    opencage_api_key: Optional[str] = None
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_phone_number: Optional[str] = None
    fcm_server_key: Optional[str] = None
    
    # Backup settings
    backup_enabled: bool = True
    backup_retention_days: int = 30
    backup_s3_bucket: Optional[str] = None
    backup_encryption_key: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        
    @validator("allowed_origins", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator("allowed_methods", pre=True)
    def parse_cors_methods(cls, v):
        if isinstance(v, str):
            return [method.strip() for method in v.split(",")]
        return v
    
    @validator("allowed_file_types", pre=True)
    def parse_file_types(cls, v):
        if isinstance(v, str):
            return [ext.strip() for ext in v.split(",")]
        return v
    
    @validator("database_url")
    def validate_database_url(cls, v):
        if not v or not v.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must be a valid PostgreSQL connection string")
        return v
    
    @validator("redis_url")
    def validate_redis_url(cls, v):
        if not v or not v.startswith("redis://"):
            raise ValueError("REDIS_URL must be a valid Redis connection string")
        return v


@lru_cache()
def get_production_settings() -> ProductionSettings:
    """Get cached production settings"""
    return ProductionSettings()


# Export settings instance
settings = get_production_settings()