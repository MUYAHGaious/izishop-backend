from datetime import datetime, timedelta
from typing import Dict, Set, Optional, List
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from models.user import User
from models.online_status import OnlineStatus
from models.shop import Shop
import logging

logger = logging.getLogger(__name__)

class OnlineStatusManager:
    def __init__(self):
        # WebSocket connections: {connection_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}
        # User connections: {user_id: set of connection_ids}
        self.user_connections: Dict[str, Set[str]] = {}
        # Connection to user mapping: {connection_id: user_id}
        self.connection_users: Dict[str, str] = {}
        
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket connection {connection_id} established")
        
    async def disconnect(self, connection_id: str, db: Session):
        """Handle WebSocket disconnection"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            
        # Get user_id associated with this connection
        user_id = self.connection_users.get(connection_id)
        if user_id:
            # Remove connection from user's connection set
            if user_id in self.user_connections:
                self.user_connections[user_id].discard(connection_id)
                # If no more connections for this user, mark as offline
                if not self.user_connections[user_id]:
                    del self.user_connections[user_id]
                    await self.set_user_offline(user_id, db)
                    
            # Remove connection-user mapping
            del self.connection_users[connection_id]
            
        logger.info(f"WebSocket connection {connection_id} disconnected")
        
    async def authenticate_user(self, connection_id: str, user_id: str, db: Session):
        """Authenticate and associate a user with a connection"""
        # Add to user connections
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)
        
        # Map connection to user
        self.connection_users[connection_id] = user_id
        
        # Set user online
        await self.set_user_online(user_id, db)
        
        # Send authentication success
        await self.send_to_connection(connection_id, {
            "type": "authentication_success",
            "user_id": user_id
        })
        
        # Send current online status to the new connection
        await self.send_bulk_status_update(connection_id, db)
        
        logger.info(f"User {user_id} authenticated on connection {connection_id}")
        
    async def set_user_online(self, user_id: str, db: Session):
        """Mark user as online and broadcast the status"""
        timestamp = datetime.utcnow()
        
        # Update or create online status record
        online_status = db.query(OnlineStatus).filter(OnlineStatus.user_id == user_id).first()
        if not online_status:
            online_status = OnlineStatus(
                user_id=user_id,
                is_online=True,
                last_seen=timestamp,
                last_heartbeat=timestamp,
                status_type="online"
            )
            db.add(online_status)
        else:
            online_status.is_online = True
            online_status.last_seen = timestamp
            online_status.last_heartbeat = timestamp
            online_status.status_type = "online"
            online_status.updated_at = timestamp
            
        # Also update user table
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_online = True
            user.last_seen = timestamp
            user.last_heartbeat = timestamp
            
        db.commit()
        
        # Get user details for broadcasting
        user_data = await self.get_user_broadcast_data(user_id, db)
        
        # Broadcast to all connected clients
        await self.broadcast_status_update({
            "type": "user_online",
            "user_id": user_id,
            "user_type": user_data.get("user_type"),
            "shop_id": user_data.get("shop_id"),
            "timestamp": timestamp.isoformat()
        })
        
    async def set_user_offline(self, user_id: str, db: Session):
        """Mark user as offline and broadcast the status"""
        timestamp = datetime.utcnow()
        
        # Update online status record
        online_status = db.query(OnlineStatus).filter(OnlineStatus.user_id == user_id).first()
        if online_status:
            online_status.is_online = False
            online_status.last_seen = timestamp
            online_status.status_type = "offline"
            online_status.updated_at = timestamp
            
        # Also update user table
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.is_online = False
            user.last_seen = timestamp
            
        db.commit()
        
        # Broadcast to all connected clients
        await self.broadcast_status_update({
            "type": "user_offline",
            "user_id": user_id,
            "last_seen": timestamp.isoformat()
        })
        
    async def update_heartbeat(self, user_id: str, db: Session):
        """Update user's heartbeat timestamp"""
        timestamp = datetime.utcnow()
        
        # Update online status record
        online_status = db.query(OnlineStatus).filter(OnlineStatus.user_id == user_id).first()
        if online_status:
            online_status.last_heartbeat = timestamp
            online_status.updated_at = timestamp
            
        # Also update user table
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.last_heartbeat = timestamp
            
        db.commit()
        
    async def get_user_broadcast_data(self, user_id: str, db: Session) -> dict:
        """Get user data needed for broadcasting"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {}
            
        user_data = {
            "user_type": user.role.value if user.role else None,
            "shop_id": None
        }
        
        # If user is a shop owner, get shop ID
        if user.role and user.role.value == "SHOP_OWNER" and user.shop:
            user_data["shop_id"] = user.shop.id
            
        return user_data
        
    async def send_to_connection(self, connection_id: str, message: dict):
        """Send message to a specific connection"""
        if connection_id in self.active_connections:
            try:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to connection {connection_id}: {e}")
                # Remove failed connection
                if connection_id in self.active_connections:
                    del self.active_connections[connection_id]
                    
    async def broadcast_status_update(self, message: dict):
        """Broadcast status update to all connected clients"""
        if not self.active_connections:
            return
            
        message_json = json.dumps(message)
        failed_connections = []
        
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.error(f"Error broadcasting to connection {connection_id}: {e}")
                failed_connections.append(connection_id)
                
        # Remove failed connections
        for connection_id in failed_connections:
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
                
    async def send_bulk_status_update(self, connection_id: str, db: Session):
        """Send current online status of all users to a new connection"""
        try:
            # Get all online users
            online_users = db.query(OnlineStatus).filter(OnlineStatus.is_online == True).all()
            
            online_user_data = []
            for status in online_users:
                user_data = await self.get_user_broadcast_data(status.user_id, db)
                online_user_data.append({
                    "user_id": status.user_id,
                    "user_type": user_data.get("user_type"),
                    "shop_id": user_data.get("shop_id"),
                    "timestamp": status.last_seen.isoformat() if status.last_seen else None
                })
                
            # Get recent offline users with last_seen data
            cutoff_time = datetime.utcnow() - timedelta(days=7)  # Last 7 days
            offline_users = db.query(OnlineStatus).filter(
                and_(
                    OnlineStatus.is_online == False,
                    OnlineStatus.last_seen >= cutoff_time
                )
            ).all()
            
            last_seen_data = []
            for status in offline_users:
                last_seen_data.append({
                    "user_id": status.user_id,
                    "last_seen": status.last_seen.isoformat() if status.last_seen else None
                })
                
            message = {
                "type": "bulk_status_update",
                "online_users": online_user_data,
                "last_seen": last_seen_data
            }
            
            await self.send_to_connection(connection_id, message)
            
        except Exception as e:
            logger.error(f"Error sending bulk status update: {e}")
            
    async def get_online_users(self, db: Session) -> List[dict]:
        """Get list of currently online users"""
        online_statuses = db.query(OnlineStatus).filter(OnlineStatus.is_online == True).all()
        
        result = []
        for status in online_statuses:
            user_data = await self.get_user_broadcast_data(status.user_id, db)
            result.append({
                "user_id": status.user_id,
                "user_type": user_data.get("user_type"),
                "shop_id": user_data.get("shop_id"),
                "last_seen": status.last_seen.isoformat() if status.last_seen else None,
                "last_heartbeat": status.last_heartbeat.isoformat() if status.last_heartbeat else None
            })
            
        return result
        
    async def get_shop_online_status(self, shop_id: str, db: Session) -> dict:
        """Get online status for a specific shop"""
        # Find shop and its owner
        shop = db.query(Shop).filter(Shop.id == shop_id).first()
        if not shop or not shop.owner_id:
            return {"is_online": False, "last_seen": None}
            
        # Check owner's online status
        online_status = db.query(OnlineStatus).filter(OnlineStatus.user_id == shop.owner_id).first()
        if not online_status:
            return {"is_online": False, "last_seen": None}
            
        return {
            "is_online": online_status.is_online,
            "last_seen": online_status.last_seen.isoformat() if online_status.last_seen else None,
            "last_heartbeat": online_status.last_heartbeat.isoformat() if online_status.last_heartbeat else None
        }
        
    async def get_online_shops(self, limit: int, db: Session) -> List[dict]:
        """Get list of shops with online owners"""
        # Query for shops whose owners are online
        online_shops = db.query(Shop).join(
            OnlineStatus, Shop.owner_id == OnlineStatus.user_id
        ).filter(
            and_(
                OnlineStatus.is_online == True,
                Shop.is_active == True
            )
        ).limit(limit).all()
        
        result = []
        for shop in online_shops:
            result.append({
                "shop_id": shop.id,
                "shop_name": shop.name,
                "owner_id": shop.owner_id,
                "owner_name": f"{shop.owner.first_name} {shop.owner.last_name}" if shop.owner else None
            })
            
        return result

# Global instance
online_status_manager = OnlineStatusManager()

async def cleanup_offline_users(db: Session):
    """Background task to mark users as offline after 5 minutes of inactivity"""
    try:
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)
        
        # Find users who haven't sent heartbeat in 5 minutes but are marked online
        stale_users = db.query(OnlineStatus).filter(
            and_(
                OnlineStatus.is_online == True,
                or_(
                    OnlineStatus.last_heartbeat < cutoff_time,
                    OnlineStatus.last_heartbeat == None
                )
            )
        ).all()
        
        for status in stale_users:
            logger.info(f"Marking user {status.user_id} as offline due to inactivity")
            await online_status_manager.set_user_offline(status.user_id, db)
            
    except Exception as e:
        logger.error(f"Error in cleanup_offline_users: {e}")

async def periodic_cleanup_task():
    """Periodic task to cleanup offline users"""
    while True:
        try:
            from database.session import get_db
            db = next(get_db())
            await cleanup_offline_users(db)
            db.close()
            await asyncio.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Error in periodic cleanup task: {e}")
            await asyncio.sleep(60)