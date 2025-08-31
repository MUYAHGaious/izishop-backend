"""
Enterprise Input Validation
Comprehensive validation using Pydantic v2 with security focus
"""
import re
import html
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, validator, Field
from email_validator import validate_email, EmailNotValidError
import phonenumbers
from phonenumbers import NumberParseException


class SecurityValidator:
    """Security-focused input validation utilities"""
    
    # Common injection patterns
    SQL_INJECTION_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)",
        r"([\'\";])",
        r"(\-\-)",
        r"(/\*.*\*/)",
        r"(\bOR\b.*\b=\b)",
        r"(\bAND\b.*\b=\b)",
    ]
    
    XSS_PATTERNS = [
        r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>",
        r"javascript:",
        r"vbscript:",
        r"onload\s*=",
        r"onerror\s*=",
        r"onclick\s*=",
    ]
    
    # Path traversal patterns
    PATH_TRAVERSAL_PATTERNS = [
        r"\.\.\/",
        r"\.\.\\",
        r"%2e%2e%2f",
        r"%2e%2e%5c",
    ]

    @classmethod
    def sanitize_html(cls, text: str) -> str:
        """Sanitize HTML to prevent XSS attacks"""
        if not text:
            return text
        
        # HTML encode special characters
        sanitized = html.escape(text, quote=True)
        
        # Remove any remaining dangerous patterns
        for pattern in cls.XSS_PATTERNS:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    @classmethod
    def detect_sql_injection(cls, text: str) -> bool:
        """Detect potential SQL injection attempts"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        
        return False
    
    @classmethod
    def detect_xss(cls, text: str) -> bool:
        """Detect potential XSS attempts"""
        if not text:
            return False
        
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    @classmethod
    def detect_path_traversal(cls, text: str) -> bool:
        """Detect potential path traversal attempts"""
        if not text:
            return False
        
        for pattern in cls.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        
        return False
    
    @classmethod
    def validate_and_sanitize(cls, text: str, max_length: int = 1000) -> str:
        """Comprehensive validation and sanitization"""
        if not text:
            return text
        
        # Length check
        if len(text) > max_length:
            raise ValueError(f"Text exceeds maximum length of {max_length} characters")
        
        # Security checks
        if cls.detect_sql_injection(text):
            raise ValueError("Potential SQL injection detected")
        
        if cls.detect_xss(text):
            raise ValueError("Potential XSS attack detected")
        
        if cls.detect_path_traversal(text):
            raise ValueError("Potential path traversal attack detected")
        
        # Sanitize and return
        return cls.sanitize_html(text)


class SecureBaseModel(BaseModel):
    """Base model with security validation"""
    
    class Config:
        # Use enum values instead of enum objects
        use_enum_values = True
        # Validate field assignment
        validate_assignment = True
        # Allow population by field name
        populate_by_name = True
        # Strip whitespace from strings
        str_strip_whitespace = True
        # Validate all fields even if not required
        validate_default = True


class EmailField(str):
    """Secure email field with validation"""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if not v:
            raise ValueError('Email is required')
        
        # Basic security check
        if SecurityValidator.detect_xss(v) or SecurityValidator.detect_sql_injection(v):
            raise ValueError('Invalid email format - security check failed')
        
        try:
            # Validate email format
            valid_email = validate_email(v)
            return valid_email.email
        except EmailNotValidError:
            raise ValueError('Invalid email format')


class PhoneField(str):
    """Secure phone field with validation"""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if not v:
            return v  # Allow empty phone numbers
        
        # Security check
        if SecurityValidator.detect_xss(v) or SecurityValidator.detect_sql_injection(v):
            raise ValueError('Invalid phone format - security check failed')
        
        try:
            # Parse and validate phone number
            phone_number = phonenumbers.parse(v, None)
            if not phonenumbers.is_valid_number(phone_number):
                raise ValueError('Invalid phone number')
            
            # Return formatted number
            return phonenumbers.format_number(phone_number, phonenumbers.PhoneNumberFormat.E164)
        except NumberParseException:
            raise ValueError('Invalid phone number format')


class SecureTextField(str):
    """Secure text field with sanitization"""
    
    def __init__(self, max_length: int = 1000, allow_html: bool = False):
        self.max_length = max_length
        self.allow_html = allow_html
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v, values=None, config=None, field=None):
        if not v:
            return v
        
        # Get max_length from field info if available
        max_length = getattr(field, 'max_length', 1000) if field else 1000
        allow_html = getattr(field, 'allow_html', False) if field else False
        
        # Validate and sanitize
        if allow_html:
            # Only sanitize XSS but allow some HTML
            if SecurityValidator.detect_xss(v):
                raise ValueError('Potentially dangerous HTML content detected')
            return SecurityValidator.sanitize_html(v)[:max_length]
        else:
            # Full sanitization
            return SecurityValidator.validate_and_sanitize(v, max_length)


# Common validation schemas
class UserRegistrationSchema(SecureBaseModel):
    """Secure user registration schema"""
    
    email: EmailField
    phone: Optional[PhoneField] = None
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    
    @validator('first_name', 'last_name')
    def validate_names(cls, v):
        if not v or not v.strip():
            raise ValueError('Name cannot be empty')
        
        # Check for security issues
        cleaned = SecurityValidator.validate_and_sanitize(v.strip(), 100)
        
        # Ensure name contains only valid characters
        if not re.match(r'^[a-zA-Z\s\'\-\.]+$', cleaned):
            raise ValueError('Name contains invalid characters')
        
        return cleaned
    
    @validator('password')
    def validate_password(cls, v):
        if not v:
            raise ValueError('Password is required')
        
        # Password strength checks
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        
        # Check for common weak passwords
        weak_patterns = [
            'password', '123456', 'qwerty', 'admin', 'letmein',
            'welcome', 'monkey', 'dragon', 'master', 'admin123'
        ]
        
        if any(pattern in v.lower() for pattern in weak_patterns):
            raise ValueError('Password contains common weak patterns')
        
        return v


class ProductCreationSchema(SecureBaseModel):
    """Secure product creation schema"""
    
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    price: float = Field(..., gt=0, le=10000000)  # Max 10M
    condition: str = Field(..., pattern=r'^(new|used_like_new|used_good|used_acceptable)$')
    category_id: str = Field(..., min_length=1)
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Product name is required')
        
        return SecurityValidator.validate_and_sanitize(v.strip(), 255)
    
    @validator('description')
    def validate_description(cls, v):
        if not v:
            return v
        
        # Allow some HTML in descriptions but sanitize dangerous content
        if SecurityValidator.detect_xss(v):
            raise ValueError('Description contains potentially dangerous content')
        
        return SecurityValidator.sanitize_html(v.strip())
    
    @validator('price')
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError('Price must be greater than 0')
        
        if v > 10000000:  # 10 million max
            raise ValueError('Price exceeds maximum allowed value')
        
        return round(v, 2)  # Round to 2 decimal places


class SearchQuerySchema(SecureBaseModel):
    """Secure search query schema"""
    
    q: Optional[str] = Field(None, max_length=200)
    category: Optional[str] = Field(None, max_length=100)
    min_price: Optional[float] = Field(None, ge=0)
    max_price: Optional[float] = Field(None, ge=0)
    condition: Optional[str] = Field(None, pattern=r'^(new|used_like_new|used_good|used_acceptable)$')
    page: int = Field(default=1, ge=1, le=1000)
    limit: int = Field(default=20, ge=1, le=100)
    
    @validator('q')
    def validate_query(cls, v):
        if not v:
            return v
        
        # Security validation for search query
        return SecurityValidator.validate_and_sanitize(v.strip(), 200)
    
    @validator('max_price')
    def validate_price_range(cls, v, values):
        if v is not None and 'min_price' in values and values['min_price'] is not None:
            if v < values['min_price']:
                raise ValueError('Max price must be greater than min price')
        return v


# Validation decorator
def validate_input(schema_class):
    """Decorator to validate input using specified schema"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extract data to validate (assume it's in kwargs)
            data = kwargs.get('data') or kwargs
            
            try:
                # Validate using schema
                validated_data = schema_class(**data)
                kwargs.update(validated_data.dict())
                return func(*args, **kwargs)
            except ValueError as e:
                raise ValueError(f"Validation error: {str(e)}")
        return wrapper
    return decorator