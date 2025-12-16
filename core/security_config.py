"""
Enterprise Security Configuration
Implements secure configuration management with validation
"""
import os
import secrets
from typing import List, Optional
from functools import lru_cache
from pydantic import validator, Field
from pydantic_settings import BaseSettings
from urllib.parse import urlparse


class SecuritySettings(BaseSettings):
    """Enterprise security configuration with validation"""
    
    # Environment
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    
    # Database Configuration
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    DATABASE_POOL_SIZE: int = Field(default=20, env="DATABASE_POOL_SIZE")
    DATABASE_MAX_OVERFLOW: int = Field(default=10, env="DATABASE_MAX_OVERFLOW")
    
    # Security Configuration
    SECRET_KEY: str = Field(..., env="SECRET_KEY", min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=480, env="ACCESS_TOKEN_EXPIRE_MINUTES")  # 8 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, env="REFRESH_TOKEN_EXPIRE_DAYS")
    ADMIN_ACCESS_CODE: str = Field(..., env="ADMIN_ACCESS_CODE", min_length=32)
    
    # JWT Configuration
    JWT_ALGORITHM: str = Field(default="HS256", env="JWT_ALGORITHM")
    JWT_AUDIENCE: str = Field(default="izishop-api", env="JWT_AUDIENCE")
    JWT_ISSUER: str = Field(default="izishop.com", env="JWT_ISSUER")
    
    # Redis Configuration
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    REDIS_PASSWORD: Optional[str] = Field(None, env="REDIS_PASSWORD")
    
    # CORS and Security Headers
    ALLOWED_ORIGINS: str = Field(default="", env="ALLOWED_ORIGINS")
    TRUSTED_HOSTS: str = Field(default="", env="TRUSTED_HOSTS")
    
    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=100, env="RATE_LIMIT_REQUESTS_PER_MINUTE")
    RATE_LIMIT_BURST: int = Field(default=20, env="RATE_LIMIT_BURST")
    
    # External API Keys
    TRANZAK_API_KEY: str = Field(default="", env="TRANZAK_API_KEY")
    TRANZAK_API_SECRET: str = Field(default="", env="TRANZAK_API_SECRET")
    TRANZAK_BASE_URL: str = Field(default="https://api.tranzak.com", env="TRANZAK_BASE_URL")
    CLOUDINARY_API_KEY: str = Field(default="", env="CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str = Field(default="", env="CLOUDINARY_API_SECRET")
    CLOUDINARY_CLOUD_NAME: str = Field(default="", env="CLOUDINARY_CLOUD_NAME")
    SENDGRID_API_KEY: str = Field(default="", env="SENDGRID_API_KEY")
    FROM_EMAIL: str = Field(default="noreply@izishop.com", env="FROM_EMAIL")
    TWILIO_AUTH_TOKEN: str = Field(default="", env="TWILIO_AUTH_TOKEN")
    TWILIO_ACCOUNT_SID: str = Field(default="", env="TWILIO_ACCOUNT_SID")
    TWILIO_PHONE_NUMBER: str = Field(default="", env="TWILIO_PHONE_NUMBER")
    
    # Application URLs
    FRONTEND_BASE_URL: str = Field(default="http://localhost:3000", env="FRONTEND_BASE_URL")
    BACKEND_BASE_URL: str = Field(default="http://localhost:8000", env="BACKEND_BASE_URL")
    
    # Monitoring
    SENTRY_DSN: Optional[str] = Field(None, env="SENTRY_DSN")
    ENABLE_METRICS: bool = Field(default=True, env="ENABLE_METRICS")

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields like MESOMB_* variables

    @validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        """Validate that SECRET_KEY is secure"""
        if v == "your-secret-key-here-change-in-production":
            raise ValueError("SECRET_KEY must be changed from default value")
        
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters long")
        
        # Check for weak patterns
        if v.lower() in ["secret", "password", "admin", "123456"]:
            raise ValueError("SECRET_KEY contains weak patterns")
            
        return v
    
    @validator("ADMIN_ACCESS_CODE")
    def validate_admin_code(cls, v):
        """Validate that ADMIN_ACCESS_CODE is secure"""
        if v in ["ADMIN2024!", "admin", "password", "123456"]:
            raise ValueError("ADMIN_ACCESS_CODE must be changed from default/weak values")
        
        if len(v) < 32:
            raise ValueError("ADMIN_ACCESS_CODE must be at least 32 characters long")
            
        return v
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v, values):
        """Validate database URL format and security"""
        parsed = urlparse(v)
        
        # Check for SQLite in production
        environment = values.get("ENVIRONMENT", "development")
        if environment == "production" and parsed.scheme == "sqlite":
            raise ValueError("SQLite not allowed in production environment")
        
        # Ensure database URL has proper format (SQLite URLs don't have netloc)
        if not parsed.scheme:
            raise ValueError("DATABASE_URL must be a valid URL")
            
        return v
    
    def get_allowed_origins_list(self) -> List[str]:
        """Parse comma-separated origins into list"""
        if not self.ALLOWED_ORIGINS:
            return []
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]
    
    def get_trusted_hosts_list(self) -> List[str]:
        """Parse comma-separated hosts into list"""
        if not self.TRUSTED_HOSTS:
            return []
        return [host.strip() for host in self.TRUSTED_HOSTS.split(",") if host.strip()]

    def generate_secure_secret(self, length: int = 64) -> str:
        """Generate a cryptographically secure secret"""
        return secrets.token_urlsafe(length)
    
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"
    
    def get_cors_origins(self) -> List[str]:
        """Get appropriate CORS origins based on environment"""
        if self.is_production():
            return self.get_allowed_origins_list()
        else:
            # Development origins
            return [
                "http://localhost:4028",
                "http://127.0.0.1:4028",
                "http://localhost:3000",
                "http://localhost:5173",
            ]


@lru_cache()
def get_security_settings() -> SecuritySettings:
    """Get cached security settings"""
    return SecuritySettings()


def validate_production_config():
    """Validate configuration for production deployment"""
    settings = get_security_settings()
    
    errors = []
    
    if settings.is_production():
        # Check for development/weak configurations
        if settings.DEBUG:
            errors.append("DEBUG must be False in production")
        
        if not settings.get_allowed_origins_list():
            errors.append("ALLOWED_ORIGINS must be configured in production")
        
        if not settings.get_trusted_hosts_list():
            errors.append("TRUSTED_HOSTS must be configured in production")
        
        # Check for missing critical secrets
        critical_secrets = [
            "SECRET_KEY", "ADMIN_ACCESS_CODE", "DATABASE_URL"
        ]
        
        for secret in critical_secrets:
            value = getattr(settings, secret, "")
            if not value or value == "":
                errors.append(f"{secret} is required in production")
    
    if errors:
        raise ValueError(f"Production configuration errors: {'; '.join(errors)}")
    
    return True


# Export settings instance
security_settings = get_security_settings()