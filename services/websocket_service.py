import asyncio
import json
import logging
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import uuid

from ..models.user import User, UserRole
from ..models.shop import Shop
from ..services.analytics_service import analytics_service

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    WebSocket connection manager for real-time analytics updates
    """
    
    def __init__(self):
        # Store active connections with metadata
        self.active_connections: Dict[str, Dict] = {}
        # Group connections by subscription type
        self.subscriptions: Dict[str, Set[str]] = {
            "analytics": set(),
            "shop_analytics": set(),
            "anomalies": set(),
            "forecasts": set()
        }
        # Store user sessions
        self.user_sessions: Dict[int, Set[str]] = {}
    
    async def connect(
        self, 
        websocket: WebSocket, 
        user: User, 
        connection_type: str = "analytics",
        filters: Dict[str, Any] = None
    ) -> str:
        """Accept WebSocket connection and register it"""
        await websocket.accept()
        
        connection_id = str(uuid.uuid4())
        
        # Store connection metadata
        self.active_connections[connection_id] = {
            "websocket": websocket,
            "user_id": user.id,
            "user_role": user.role.value,
            "connection_type": connection_type,
            "filters": filters or {},
            "connected_at": datetime.utcnow(),
            "last_activity": datetime.utcnow()
        }
        
        # Add to subscriptions
        if connection_type in self.subscriptions:
            self.subscriptions[connection_type].add(connection_id)
        
        # Track user sessions
        if user.id not in self.user_sessions:
            self.user_sessions[user.id] = set()
        self.user_sessions[user.id].add(connection_id)
        
        logger.info(f"WebSocket connection established: {connection_id} for user {user.id}")
        
        # Send welcome message
        await self.send_personal_message(connection_id, {
            "type": "connection_established",
            "connection_id": connection_id,
            "user_role": user.role.value,
            "subscriptions": [connection_type],
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return connection_id
    
    def disconnect(self, connection_id: str):
        """Remove connection"""
        if connection_id in self.active_connections:
            connection_info = self.active_connections[connection_id]
            user_id = connection_info["user_id"]
            
            # Remove from all subscriptions
            for subscription_set in self.subscriptions.values():
                subscription_set.discard(connection_id)
            
            # Remove from user sessions
            if user_id in self.user_sessions:
                self.user_sessions[user_id].discard(connection_id)
                if not self.user_sessions[user_id]:
                    del self.user_sessions[user_id]
            
            # Remove connection
            del self.active_connections[connection_id]
            
            logger.info(f"WebSocket connection closed: {connection_id}")
    
    async def send_personal_message(self, connection_id: str, message: Dict):
        """Send message to specific connection"""
        if connection_id in self.active_connections:
            try:
                websocket = self.active_connections[connection_id]["websocket"]
                await websocket.send_text(json.dumps(message))
                
                # Update last activity
                self.active_connections[connection_id]["last_activity"] = datetime.utcnow()
            except Exception as e:
                logger.error(f"Error sending message to {connection_id}: {str(e)}")
                self.disconnect(connection_id)
    
    async def broadcast_to_subscription(self, subscription_type: str, message: Dict, filters: Dict[str, Any] = None):
        """Broadcast message to all connections in a subscription"""
        if subscription_type not in self.subscriptions:
            return
        
        connections_to_remove = []
        
        for connection_id in self.subscriptions[subscription_type].copy():
            if connection_id not in self.active_connections:
                connections_to_remove.append(connection_id)
                continue
            
            connection_info = self.active_connections[connection_id]
            
            # Apply role-based filtering
            if not self._check_access_permission(connection_info, message, filters):
                continue
            
            try:
                await self.send_personal_message(connection_id, message)
            except Exception as e:
                logger.error(f"Error broadcasting to {connection_id}: {str(e)}")
                connections_to_remove.append(connection_id)
        
        # Clean up failed connections
        for connection_id in connections_to_remove:
            self.disconnect(connection_id)
    
    def _check_access_permission(self, connection_info: Dict, message: Dict, filters: Dict[str, Any] = None) -> bool:
        """Check if connection has permission to receive this message"""
        user_role = connection_info["user_role"]
        connection_filters = connection_info.get("filters", {})
        
        # Admin can see everything
        if user_role == UserRole.ADMIN.value:
            return True
        
        # Shop owners can only see their own data
        if user_role == UserRole.SHOP_OWNER.value:
            message_shop_id = message.get("shop_id") or (filters and filters.get("shop_id"))
            connection_shop_id = connection_filters.get("shop_id")
            
            if message_shop_id and connection_shop_id:
                return message_shop_id == connection_shop_id
            
            # If no shop filter is specified, allow the message
            return True
        
        # Other roles have no analytics access by default
        return False
    
    async def send_chart_update(self, metric_type: str, chart_data: Dict[str, Any]):
        """Send real-time chart updates"""
        message = {
            "type": "chart_update",
            "metric_type": metric_type,
            "data": chart_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_subscription("analytics", message)
        await self.broadcast_to_subscription("shop_analytics", message)
    
    async def send_anomaly_alert(self, anomaly_data: Dict[str, Any]):
        """Send real-time anomaly alerts"""
        message = {
            "type": "anomaly_alert",
            "anomaly": anomaly_data,
            "severity": anomaly_data.get("severity", "medium"),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_subscription("anomalies", message)
        await self.broadcast_to_subscription("analytics", message)
    
    async def send_forecast_update(self, metric_type: str, forecast_data: List[Dict[str, Any]]):
        """Send forecast updates"""
        message = {
            "type": "forecast_update",
            "metric_type": metric_type,
            "forecasts": forecast_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_subscription("forecasts", message)
        await self.broadcast_to_subscription("analytics", message)
    
    async def send_metric_update(self, event_data: Dict[str, Any]):
        """Send real-time metric updates based on events"""
        message = {
            "type": "metric_update",
            "event": event_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Include shop_id in message if present
        if "shop_id" in event_data:
            message["shop_id"] = event_data["shop_id"]
        
        await self.broadcast_to_subscription("analytics", message)
        await self.broadcast_to_subscription("shop_analytics", message)
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get statistics about active connections"""
        total_connections = len(self.active_connections)
        
        # Count by role
        role_counts = {}
        type_counts = {}
        
        for connection_info in self.active_connections.values():
            role = connection_info["user_role"]
            conn_type = connection_info["connection_type"]
            
            role_counts[role] = role_counts.get(role, 0) + 1
            type_counts[conn_type] = type_counts.get(conn_type, 0) + 1
        
        # Count by subscription
        subscription_counts = {
            sub_type: len(connections) 
            for sub_type, connections in self.subscriptions.items()
        }
        
        return {
            "total_connections": total_connections,
            "unique_users": len(self.user_sessions),
            "by_role": role_counts,
            "by_type": type_counts,
            "by_subscription": subscription_counts,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def cleanup_inactive_connections(self, timeout_minutes: int = 30):
        """Clean up inactive connections"""
        timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        connections_to_remove = []
        
        for connection_id, connection_info in self.active_connections.items():
            if connection_info["last_activity"] < timeout_threshold:
                connections_to_remove.append(connection_id)
        
        for connection_id in connections_to_remove:
            try:
                await self.send_personal_message(connection_id, {
                    "type": "connection_timeout",
                    "reason": "Inactive connection timeout",
                    "timestamp": datetime.utcnow().isoformat()
                })
            except:
                pass  # Connection might already be closed
            
            self.disconnect(connection_id)
        
        if connections_to_remove:
            logger.info(f"Cleaned up {len(connections_to_remove)} inactive connections")

# Global connection manager instance
manager = ConnectionManager()

class AnalyticsWebSocketService:
    """
    Service for handling analytics-specific WebSocket operations
    """
    
    def __init__(self, connection_manager: ConnectionManager):
        self.manager = connection_manager
        self.event_processors = {
            "order_created": self.process_order_event,
            "payment_completed": self.process_payment_event,
            "user_registered": self.process_user_event,
        }
    
    async def handle_realtime_event(self, db: Session, event_data: Dict[str, Any]):
        """
        Handle real-time events and broadcast updates to connected clients
        """
        try:
            event_type = event_data.get("event_type")
            
            # Process the event in analytics service
            await analytics_service.process_realtime_event(db, event_data)
            
            # Send real-time update to connected clients
            await self.manager.send_metric_update(event_data)
            
            # Process specific event types
            if event_type in self.event_processors:
                await self.event_processors[event_type](db, event_data)
            
            logger.info(f"Processed real-time event: {event_type}")
            
        except Exception as e:
            logger.error(f"Error handling real-time event: {str(e)}")
            raise
    
    async def process_order_event(self, db: Session, event_data: Dict[str, Any]):
        """Process order-related events"""
        try:
            # Get updated order metrics
            shop_id = event_data.get("shop_id")
            
            # Get real-time chart data for orders
            chart_data = await analytics_service.get_realtime_chart_data(
                db, "orders", "1h", shop_id=shop_id
            )
            
            # Broadcast chart update
            await self.manager.send_chart_update("orders", chart_data)
            
        except Exception as e:
            logger.error(f"Error processing order event: {str(e)}")
    
    async def process_payment_event(self, db: Session, event_data: Dict[str, Any]):
        """Process payment-related events"""
        try:
            shop_id = event_data.get("shop_id")
            
            # Get updated revenue metrics
            chart_data = await analytics_service.get_realtime_chart_data(
                db, "revenue", "1h", shop_id=shop_id
            )
            
            # Broadcast chart update
            await self.manager.send_chart_update("revenue", chart_data)
            
            # Check for revenue anomalies
            anomalies = await analytics_service.get_recent_anomalies(
                db, "revenue", shop_id
            )
            
            # Send anomaly alerts if any
            for anomaly in anomalies:
                if anomaly.get("severity") in ["high", "critical"]:
                    await self.manager.send_anomaly_alert(anomaly)
            
        except Exception as e:
            logger.error(f"Error processing payment event: {str(e)}")
    
    async def process_user_event(self, db: Session, event_data: Dict[str, Any]):
        """Process user-related events"""
        try:
            # Get updated user metrics (admin only)
            chart_data = await analytics_service.get_realtime_chart_data(
                db, "users", "1h"
            )
            
            # Broadcast chart update
            await self.manager.send_chart_update("users", chart_data)
            
        except Exception as e:
            logger.error(f"Error processing user event: {str(e)}")
    
    async def schedule_forecast_updates(self, db: Session):
        """
        Schedule periodic forecast updates (can be called by a background task)
        """
        try:
            # Generate forecasts for key metrics
            for metric_type in ["revenue", "orders"]:
                forecasts = await analytics_service.generate_forecast(
                    db, metric_type, days_ahead=7
                )
                
                if forecasts:
                    await self.manager.send_forecast_update(metric_type, forecasts)
            
            logger.info("Forecast updates sent to connected clients")
            
        except Exception as e:
            logger.error(f"Error sending forecast updates: {str(e)}")

# Global analytics WebSocket service instance
analytics_ws_service = AnalyticsWebSocketService(manager)