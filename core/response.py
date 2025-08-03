"""
Standardized API response models for consistent data structure
"""
from typing import Any, Dict, List, Optional, Generic, TypeVar, Union
from pydantic import BaseModel, Field
from datetime import datetime

T = TypeVar('T')


class APIResponse(BaseModel, Generic[T]):
    """Standard API response wrapper"""
    success: bool = Field(description="Indicates if the request was successful")
    message: str = Field(description="Human-readable message")
    data: Optional[T] = Field(None, description="Response data")
    errors: Optional[List[Dict[str, Any]]] = Field(None, description="Error details if any")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    page: int = Field(description="Current page number")
    per_page: int = Field(description="Items per page")
    total_items: int = Field(description="Total number of items")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there are more pages")
    has_prev: bool = Field(description="Whether there are previous pages")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""
    success: bool = True
    message: str = "Data retrieved successfully"
    data: List[T] = Field(description="List of items")
    pagination: PaginationMeta = Field(description="Pagination metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EmptyDataResponse(BaseModel):
    """Response for when no data is available"""
    success: bool = True
    message: str = "No data available"
    data: Union[List, Dict] = Field(description="Empty data structure")
    reason: Optional[str] = Field(None, description="Reason why no data is available")
    suggestions: Optional[List[str]] = Field(None, description="Suggested actions")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response model"""
    success: bool = False
    message: str = Field(description="Error message")
    error_code: Optional[str] = Field(None, description="Error code for programmatic handling")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


def success_response(
    data: Any = None,
    message: str = "Operation successful",
    meta: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a success response"""
    return {
        "success": True,
        "message": message,
        "data": data,
        "meta": meta,
        "timestamp": datetime.utcnow().isoformat()
    }


def error_response(
    message: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create an error response"""
    return {
        "success": False,
        "message": message,
        "error_code": error_code,
        "details": details,
        "timestamp": datetime.utcnow().isoformat()
    }


def empty_data_response(
    data_type: str,
    reason: Optional[str] = None,
    suggestions: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Create an empty data response"""
    return {
        "success": True,
        "message": f"No {data_type} available",
        "data": [],
        "reason": reason,
        "suggestions": suggestions or [
            f"Try creating new {data_type}",
            "Check your filters or search criteria",
            "Contact support if this seems incorrect"
        ],
        "timestamp": datetime.utcnow().isoformat()
    }


def paginated_response(
    data: List[Any],
    page: int,
    per_page: int,
    total_items: int,
    message: str = "Data retrieved successfully"
) -> Dict[str, Any]:
    """Create a paginated response"""
    total_pages = (total_items + per_page - 1) // per_page
    
    return {
        "success": True,
        "message": message,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "timestamp": datetime.utcnow().isoformat()
    }