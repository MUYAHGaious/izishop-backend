from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import json
import logging
import asyncio

from ..database import get_db
from ..models.user import User, UserRole
from ..models.shop import Shop
from ..auth import get_current_user_from_token
from ..services.websocket_service import manager, analytics_ws_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/analytics")
async def websocket_analytics_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    connection_type: str = Query("analytics"),
    shop_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time analytics updates
    """
    connection_id = None
    
    try:
        # Authenticate user from token
        if not token:
            await websocket.close(code=4001, reason="Authentication required")
            return
        
        try:
            user = await get_current_user_from_token(token, db)
        except Exception as e:
            await websocket.close(code=4001, reason="Invalid token")
            return
        
        # Check analytics access
        if user.role not in [UserRole.ADMIN, UserRole.SHOP_OWNER]:
            await websocket.close(code=4003, reason="Analytics access denied")
            return
        
        # For shop owners, validate shop access
        user_shop_id = shop_id
        if user.role == UserRole.SHOP_OWNER:
            user_shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if user_shop:
                user_shop_id = user_shop.id
            else:
                await websocket.close(code=4004, reason="No shop found for user")
                return
        
        # Prepare connection filters
        filters = {}
        if user_shop_id:
            filters["shop_id"] = user_shop_id
        
        # Establish connection
        connection_id = await manager.connect(
            websocket, 
            user, 
            connection_type,
            filters
        )
        
        logger.info(f"Analytics WebSocket connected: {connection_id} for user {user.id}")
        
        # Send initial data
        await send_initial_analytics_data(connection_id, user, user_shop_id, db)
        
        # Listen for messages
        while True:
            try:
                # Set a timeout for receiving messages
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                await handle_websocket_message(connection_id, message, user, db)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await manager.send_personal_message(connection_id, {
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat()
                })
                continue
                
    except WebSocketDisconnect:
        logger.info(f"Analytics WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        if connection_id:
            manager.disconnect(connection_id)

async def send_initial_analytics_data(connection_id: str, user: User, shop_id: Optional[int], db: Session):
    """Send initial analytics data when client connects"""
    try:
        from ..services.analytics_service import analytics_service
        from datetime import datetime
        
        # Send connection confirmation
        await manager.send_personal_message(connection_id, {
            "type": "initial_data",
            "user_role": user.role.value,
            "shop_id": shop_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Send current chart data for key metrics
        metrics_to_send = ["revenue", "orders"]
        if user.role == UserRole.ADMIN:
            metrics_to_send.append("users")
        
        for metric_type in metrics_to_send:
            try:
                chart_data = await analytics_service.get_realtime_chart_data(
                    db, metric_type, "24h", shop_id=shop_id,
                    user_id=user.id, user_role=user.role.value
                )
                
                await manager.send_personal_message(connection_id, {
                    "type": "initial_chart_data",
                    "metric_type": metric_type,
                    "data": chart_data,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                logger.error(f"Error sending initial data for {metric_type}: {str(e)}")
        
        # Send recent anomalies
        try:
            anomalies = []
            for metric_type in ["revenue", "orders"]:
                metric_anomalies = await analytics_service.get_recent_anomalies(
                    db, metric_type, shop_id
                )
                anomalies.extend(metric_anomalies[:3])  # Latest 3 per metric
            
            if anomalies:
                await manager.send_personal_message(connection_id, {
                    "type": "initial_anomalies",
                    "anomalies": anomalies,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
        except Exception as e:
            logger.error(f"Error sending initial anomalies: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error sending initial analytics data: {str(e)}")

async def handle_websocket_message(connection_id: str, message: str, user: User, db: Session):
    """Handle incoming WebSocket messages"""
    try:
        data = json.loads(message)
        message_type = data.get("type")
        
        if message_type == "subscribe":
            # Handle subscription requests
            await handle_subscription_request(connection_id, data, user, db)
            
        elif message_type == "get_chart_data":
            # Handle chart data requests
            await handle_chart_data_request(connection_id, data, user, db)
            
        elif message_type == "get_forecasts":
            # Handle forecast requests
            await handle_forecast_request(connection_id, data, user, db)
            
        elif message_type == "acknowledge_anomaly":
            # Handle anomaly acknowledgment
            await handle_anomaly_acknowledgment(connection_id, data, user, db)
            
        elif message_type == "pong":
            # Handle pong response
            await manager.send_personal_message(connection_id, {
                "type": "pong_received",
                "timestamp": datetime.utcnow().isoformat()
            })
            
        else:
            await manager.send_personal_message(connection_id, {
                "type": "error",
                "message": f"Unknown message type: {message_type}",
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except json.JSONDecodeError:
        await manager.send_personal_message(connection_id, {
            "type": "error",
            "message": "Invalid JSON format",
            "timestamp": datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {str(e)}")
        await manager.send_personal_message(connection_id, {
            "type": "error",
            "message": "Internal server error",
            "timestamp": datetime.utcnow().isoformat()
        })

async def handle_subscription_request(connection_id: str, data: Dict[str, Any], user: User, db: Session):
    """Handle subscription requests"""
    try:
        subscription_type = data.get("subscription_type")
        filters = data.get("filters", {})
        
        # Validate subscription type
        valid_subscriptions = ["analytics", "anomalies", "forecasts"]
        if subscription_type not in valid_subscriptions:
            await manager.send_personal_message(connection_id, {
                "type": "subscription_error",
                "message": f"Invalid subscription type: {subscription_type}",
                "timestamp": datetime.utcnow().isoformat()
            })
            return
        
        # Update connection subscription
        if connection_id in manager.active_connections:
            connection_info = manager.active_connections[connection_id]
            connection_info["connection_type"] = subscription_type
            connection_info["filters"].update(filters)
            
            # Add to subscription group
            manager.subscriptions[subscription_type].add(connection_id)
            
            await manager.send_personal_message(connection_id, {
                "type": "subscription_confirmed",
                "subscription_type": subscription_type,
                "filters": filters,
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Error handling subscription request: {str(e)}")

async def handle_chart_data_request(connection_id: str, data: Dict[str, Any], user: User, db: Session):
    """Handle chart data requests"""
    try:
        from ..services.analytics_service import analytics_service
        from datetime import datetime
        
        metric_type = data.get("metric_type")
        time_range = data.get("time_range", "24h")
        filters = data.get("filters", {})
        
        # Get shop ID for shop owners
        shop_id = filters.get("shop_id")
        if user.role == UserRole.SHOP_OWNER:
            user_shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if user_shop:
                shop_id = user_shop.id
        
        # Get chart data
        chart_data = await analytics_service.get_realtime_chart_data(
            db, metric_type, time_range, 
            shop_id=shop_id,
            category_id=filters.get("category_id"),
            region=filters.get("region"),
            user_id=user.id,
            user_role=user.role.value
        )
        
        await manager.send_personal_message(connection_id, {
            "type": "chart_data_response",
            "metric_type": metric_type,
            "data": chart_data,
            "request_id": data.get("request_id"),
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error handling chart data request: {str(e)}")
        await manager.send_personal_message(connection_id, {
            "type": "chart_data_error",
            "message": str(e),
            "request_id": data.get("request_id"),
            "timestamp": datetime.utcnow().isoformat()
        })

async def handle_forecast_request(connection_id: str, data: Dict[str, Any], user: User, db: Session):
    """Handle forecast requests"""
    try:
        from ..services.analytics_service import analytics_service
        from datetime import datetime
        
        metric_type = data.get("metric_type")
        days_ahead = data.get("days_ahead", 7)
        filters = data.get("filters", {})
        
        # Get shop ID for shop owners
        shop_id = filters.get("shop_id")
        if user.role == UserRole.SHOP_OWNER:
            user_shop = db.query(Shop).filter(Shop.owner_id == user.id).first()
            if user_shop:
                shop_id = user_shop.id
        
        # Generate forecasts
        forecasts = await analytics_service.generate_forecast(
            db, metric_type, days_ahead,
            shop_id=shop_id,
            category_id=filters.get("category_id"),
            region=filters.get("region")
        )
        
        await manager.send_personal_message(connection_id, {
            "type": "forecast_response",
            "metric_type": metric_type,
            "forecasts": forecasts,
            "request_id": data.get("request_id"),
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error handling forecast request: {str(e)}")
        await manager.send_personal_message(connection_id, {
            "type": "forecast_error",
            "message": str(e),
            "request_id": data.get("request_id"),
            "timestamp": datetime.utcnow().isoformat()
        })

async def handle_anomaly_acknowledgment(connection_id: str, data: Dict[str, Any], user: User, db: Session):
    """Handle anomaly acknowledgment"""
    try:
        from ..models.analytics import AnomalyDetection
        from datetime import datetime
        
        detection_id = data.get("detection_id")
        
        # Find and acknowledge the anomaly
        anomaly = db.query(AnomalyDetection).filter(
            AnomalyDetection.detection_id == detection_id
        ).first()
        
        if anomaly:
            anomaly.acknowledged = True
            anomaly.acknowledged_by = user.id
            anomaly.acknowledged_at = datetime.utcnow()
            db.commit()
            
            await manager.send_personal_message(connection_id, {
                "type": "anomaly_acknowledged",
                "detection_id": detection_id,
                "acknowledged_by": user.id,
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            await manager.send_personal_message(connection_id, {
                "type": "anomaly_not_found",
                "detection_id": detection_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
    except Exception as e:
        logger.error(f"Error handling anomaly acknowledgment: {str(e)}")

@router.get("/ws/stats")
async def get_websocket_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get WebSocket connection statistics (admin only)"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    
    return {
        "success": True,
        "stats": manager.get_connection_stats()
    }