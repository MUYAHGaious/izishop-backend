from decouple import config

class Settings:
    DATABASE_URL: str = config("DATABASE_URL")
    SECRET_KEY: str = config("SECRET_KEY")
    TRANZAK_API_KEY: str = config("TRANZAK_API_KEY")
    TRANZAK_API_SECRET: str = config("TRANZAK_API_SECRET")
    TRANZAK_BASE_URL: str = config("TRANZAK_BASE_URL")
    CLOUDINARY_CLOUD_NAME: str = config("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY: str = config("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str = config("CLOUDINARY_API_SECRET")
    REDIS_URL: str = config("REDIS_URL")
    SENDGRID_API_KEY: str = config("SENDGRID_API_KEY")
    FROM_EMAIL: str = config("FROM_EMAIL")
    TWILIO_ACCOUNT_SID: str = config("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN: str = config("TWILIO_AUTH_TOKEN")
    TWILIO_PHONE_NUMBER: str = config("TWILIO_PHONE_NUMBER")
    FRONTEND_BASE_URL: str = config("FRONTEND_BASE_URL")
    BACKEND_BASE_URL: str = config("BACKEND_BASE_URL")

settings = Settings() 