from decouple import config

class Settings:
    # Database Configuration
    DATABASE_URL: str = config("DATABASE_URL", default="sqlite:///./izishop.db")
    
    # Security Configuration
    SECRET_KEY: str = config("SECRET_KEY", default="your-secret-key-here-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
    
    # API Configuration
    TRANZAK_API_KEY: str = config("TRANZAK_API_KEY", default="")
    TRANZAK_API_SECRET: str = config("TRANZAK_API_SECRET", default="")
    TRANZAK_BASE_URL: str = config("TRANZAK_BASE_URL", default="https://api.tranzak.com")
    
    # Storage Configuration
    CLOUDINARY_CLOUD_NAME: str = config("CLOUDINARY_CLOUD_NAME", default="")
    CLOUDINARY_API_KEY: str = config("CLOUDINARY_API_KEY", default="")
    CLOUDINARY_API_SECRET: str = config("CLOUDINARY_API_SECRET", default="")
    
    # Cache Configuration
    REDIS_URL: str = config("REDIS_URL", default="redis://localhost:6379")
    
    # Email Configuration
    SENDGRID_API_KEY: str = config("SENDGRID_API_KEY", default="")
    FROM_EMAIL: str = config("FROM_EMAIL", default="noreply@izishop.com")
    
    # SMS Configuration
    TWILIO_ACCOUNT_SID: str = config("TWILIO_ACCOUNT_SID", default="")
    TWILIO_AUTH_TOKEN: str = config("TWILIO_AUTH_TOKEN", default="")
    TWILIO_PHONE_NUMBER: str = config("TWILIO_PHONE_NUMBER", default="")
    
    # URL Configuration
    FRONTEND_BASE_URL: str = config("FRONTEND_BASE_URL", default="http://localhost:3000")
    BACKEND_BASE_URL: str = config("BACKEND_BASE_URL", default="http://localhost:8000")
    
    # Environment
    ENVIRONMENT: str = config("ENVIRONMENT", default="development")
    DEBUG: bool = config("DEBUG", default=True, cast=bool)
    
    # Logging
    LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")

settings = Settings() 