from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from ..database import get_db
from ..models.user import User, UserRole
from ..schemas.user import UserResponse
from ..auth import get_current_user
from ..services.analytics_service import analytics_service
from ..models.analytics import AnalyticsAuditLog

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)

def check_analytics_access(current_user: User, required_role: UserRole = UserRole.ADMIN):
    """Check if user has access to analytics features"""
    if current_user.role not in [UserRole.ADMIN, UserRole.SHOP_OWNER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analytics access requires admin or shop owner privileges"
        )
    
    if required_role == UserRole.ADMIN and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

@router.get("/charts/realtime/{metric_type}")
async def get_realtime_chart_data(
    metric_type: str,
    request: Request,
    time_range: str = Query("24h", description="Time range: 1h, 24h, 7d, 30d, 90d"),
    granularity: str = Query("auto", description="Data granularity: auto, hourly, daily"),
    shop_id: Optional[int] = Query(None, description="Filter by shop ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    region: Optional[str] = Query(None, description="Filter by region"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get real-time chart data with dynamic filtering and role-based access
    """
    try:
        check_analytics_access(current_user)
        
        # Shop owners can only see their own data
        if current_user.role == UserRole.SHOP_OWNER:
            # Get user's shop ID
            user_shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
            if user_shop:
                shop_id = user_shop.id
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No shop found for this user"
                )
        
        # Validate metric type
        valid_metrics = ["revenue", "orders", "users", "sessions", "conversion", "average_order_value"]
        if metric_type not in valid_metrics:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid metric type. Valid options: {', '.join(valid_metrics)}"
            )
        
        # Auto-determine granularity based on time range
        if granularity == "auto":
            if time_range in ["1h", "24h"]:
                granularity = "hourly"
            else:
                granularity = "daily"
        
        # Get chart data
        chart_data = await analytics_service.get_realtime_chart_data(
            db=db,
            metric_type=metric_type,
            time_range=time_range,
            granularity=granularity,
            shop_id=shop_id,
            category_id=category_id,
            region=region,
            user_id=current_user.id,
            user_role=current_user.role.value
        )
        
        return {
            "success": True,
            "data": chart_data,
            "metadata": {
                "user_role": current_user.role.value,
                "access_level": "shop_specific" if current_user.role == UserRole.SHOP_OWNER else "platform_wide",
                "generated_at": datetime.utcnow().isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chart data: {str(e)}")
        
        # Log failed access attempt
        await analytics_service.log_audit_event(
            db, current_user.id, current_user.role.value, 
            "view_chart", f"{metric_type}_chart",
            status="failed", error_message=str(e),
            ip_address=request.client.host
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chart data"
        )

@router.get("/forecasts/{metric_type}")
async def get_forecasts(
    metric_type: str,
    request: Request,
    days_ahead: int = Query(7, ge=1, le=30, description="Days to forecast ahead"),
    shop_id: Optional[int] = Query(None, description="Filter by shop ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    region: Optional[str] = Query(None, description="Filter by region"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get ML-based forecasts for metrics
    """
    try:
        check_analytics_access(current_user)
        
        # Shop owners can only see their own forecasts
        if current_user.role == UserRole.SHOP_OWNER:
            user_shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
            if user_shop:
                shop_id = user_shop.id
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No shop found for this user"
                )
        
        # Generate new forecasts if needed
        forecasts = await analytics_service.generate_forecast(
            db=db,
            metric_type=metric_type,
            days_ahead=days_ahead,
            shop_id=shop_id,
            category_id=category_id,
            region=region
        )
        
        # Log access
        await analytics_service.log_audit_event(
            db, current_user.id, current_user.role.value,
            "view_forecast", f"{metric_type}_forecast",
            filters_applied={
                "shop_id": shop_id, "category_id": category_id,
                "region": region, "days_ahead": days_ahead
            },
            ip_address=request.client.host
        )
        
        return {
            "success": True,
            "metric_type": metric_type,
            "forecasts": forecasts,
            "metadata": {
                "days_ahead": days_ahead,
                "model_type": "linear_regression",
                "confidence_level": 0.95,
                "generated_at": datetime.utcnow().isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting forecasts: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve forecasts"
        )

@router.get("/anomalies")
async def get_anomalies(
    request: Request,
    metric_type: Optional[str] = Query(None, description="Filter by metric type"),
    shop_id: Optional[int] = Query(None, description="Filter by shop ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    region: Optional[str] = Query(None, description="Filter by region"),
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical"),
    hours_back: int = Query(24, ge=1, le=168, description="Hours to look back"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get anomaly detections with filtering
    """
    try:
        check_analytics_access(current_user)
        
        # Shop owners can only see their own anomalies
        if current_user.role == UserRole.SHOP_OWNER:
            user_shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
            if user_shop:
                shop_id = user_shop.id
            else:
                return {"success": True, "anomalies": [], "metadata": {"total": 0}}
        
        # Get anomalies from service
        if metric_type:
            anomalies = await analytics_service.get_recent_anomalies(
                db, metric_type, shop_id, category_id, region
            )
        else:
            # Get anomalies for all metric types
            anomalies = []
            for mt in ["revenue", "orders", "users"]:
                mt_anomalies = await analytics_service.get_recent_anomalies(
                    db, mt, shop_id, category_id, region
                )
                anomalies.extend(mt_anomalies)
        
        # Filter by severity if specified
        if severity:
            anomalies = [a for a in anomalies if a.get("severity") == severity]
        
        # Log access
        await analytics_service.log_audit_event(
            db, current_user.id, current_user.role.value,
            "view_anomalies", "anomaly_detection",
            filters_applied={
                "metric_type": metric_type, "shop_id": shop_id,
                "category_id": category_id, "region": region,
                "severity": severity, "hours_back": hours_back
            },
            ip_address=request.client.host
        )
        
        return {
            "success": True,
            "anomalies": anomalies,
            "metadata": {
                "total": len(anomalies),
                "filters": {
                    "metric_type": metric_type,
                    "severity": severity,
                    "hours_back": hours_back
                },
                "generated_at": datetime.utcnow().isoformat()
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting anomalies: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve anomalies"
        )

@router.post("/events/realtime")
async def process_realtime_event(
    event_data: Dict[str, Any],
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process real-time events (for internal use or webhooks)
    """
    try:
        check_analytics_access(current_user, UserRole.ADMIN)
        
        # Process the event
        result = await analytics_service.process_realtime_event(db, event_data)
        
        # Log the processing
        await analytics_service.log_audit_event(
            db, current_user.id, current_user.role.value,
            "process_event", "realtime_event",
            filters_applied={"event_type": event_data.get("event_type")},
            ip_address=request.client.host
        )
        
        return {
            "success": True,
            "result": result,
            "processed_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing realtime event: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process realtime event"
        )

@router.get("/audit-logs")
async def get_audit_logs(
    request: Request,
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to retrieve"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource: Optional[str] = Query(None, description="Filter by resource"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get audit logs (admin only)
    """
    try:
        check_analytics_access(current_user, UserRole.ADMIN)
        
        # Build query
        query = db.query(AnalyticsAuditLog)
        
        # Apply filters
        if user_id:
            query = query.filter(AnalyticsAuditLog.user_id == user_id)
        if action:
            query = query.filter(AnalyticsAuditLog.action == action)
        if resource:
            query = query.filter(AnalyticsAuditLog.resource == resource)
        if start_date:
            query = query.filter(AnalyticsAuditLog.timestamp >= start_date)
        if end_date:
            query = query.filter(AnalyticsAuditLog.timestamp <= end_date)
        
        # Get total count
        total = query.count()
        
        # Get paginated results
        logs = query.order_by(AnalyticsAuditLog.timestamp.desc()).offset(offset).limit(limit).all()
        
        # Format response
        formatted_logs = []
        for log in logs:
            formatted_logs.append({
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "user_id": log.user_id,
                "user_role": log.user_role,
                "action": log.action,
                "resource": log.resource,
                "status": log.status,
                "ip_address": log.ip_address,
                "filters_applied": log.filters_applied,
                "time_range": log.time_range,
                "error_message": log.error_message
            })
        
        # Log this audit access
        await analytics_service.log_audit_event(
            db, current_user.id, current_user.role.value,
            "view_audit_logs", "audit_logs",
            ip_address=request.client.host
        )
        
        return {
            "success": True,
            "logs": formatted_logs,
            "metadata": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(formatted_logs)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit logs: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )

@router.get("/dashboard/overview")
async def get_analytics_overview(
    request: Request,
    time_range: str = Query("7d", description="Time range for overview"),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get analytics dashboard overview with key metrics
    """
    try:
        check_analytics_access(current_user)
        
        shop_id = None
        if current_user.role == UserRole.SHOP_OWNER:
            user_shop = db.query(Shop).filter(Shop.owner_id == current_user.id).first()
            if user_shop:
                shop_id = user_shop.id
        
        # Get key metrics
        revenue_data = await analytics_service.get_realtime_chart_data(
            db, "revenue", time_range, shop_id=shop_id,
            user_id=current_user.id, user_role=current_user.role.value
        )
        
        orders_data = await analytics_service.get_realtime_chart_data(
            db, "orders", time_range, shop_id=shop_id,
            user_id=current_user.id, user_role=current_user.role.value
        )
        
        users_data = await analytics_service.get_realtime_chart_data(
            db, "users", time_range, shop_id=shop_id,
            user_id=current_user.id, user_role=current_user.role.value
        ) if current_user.role == UserRole.ADMIN else None
        
        # Get recent anomalies
        anomalies = []
        for metric_type in ["revenue", "orders"]:
            metric_anomalies = await analytics_service.get_recent_anomalies(
                db, metric_type, shop_id
            )
            anomalies.extend(metric_anomalies)
        
        # Log access
        await analytics_service.log_audit_event(
            db, current_user.id, current_user.role.value,
            "view_overview", "analytics_overview",
            time_range=time_range,
            ip_address=request.client.host
        )
        
        return {
            "success": True,
            "overview": {
                "revenue": revenue_data,
                "orders": orders_data,
                "users": users_data,
                "anomalies": anomalies[:5],  # Latest 5 anomalies
                "time_range": time_range,
                "user_role": current_user.role.value,
                "shop_specific": shop_id is not None
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics overview: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics overview"
        )