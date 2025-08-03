import uuid
import json
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database.connection import get_db
from services.auth import get_current_user, verify_token
from services.online_status_service import online_status_manager
from models.user import User
from models.online_status import OnlineStatus

logger = logging.getLogger(__name__)
security = HTTPBearer()
router = APIRouter(prefix="/online-status", tags=["online-status"])

# Pydantic models
class OnlineStatusUpdate(BaseModel):
    status: str = "online"
    timestamp: str

class HeartbeatRequest(BaseModel):
    timestamp: str

# WebSocket endpoint for real-time online status
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    connection_id = str(uuid.uuid4())
    user_id = None
    
    try:
        await online_status_manager.connect(websocket, connection_id)
        logger.info(f"WebSocket connection established: {connection_id}")
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "authenticate":
                    # Authenticate user
                    user_id = message.get("user_id")
                    access_token = message.get("access_token")
                    
                    if not user_id or not access_token:
                        await websocket.send_text(json.dumps({
                            "type": "authentication_failed",
                            "error": "Missing user_id or access_token"
                        }))
                        continue
                        
                    # Verify token
                    try:
                        token_data = verify_token(access_token)
                        if token_data.get("user_id") != user_id:
                            raise HTTPException(status_code=401, detail="Token user mismatch")
                            
                        # Authenticate the connection
                        await online_status_manager.authenticate_user(connection_id, user_id, db)
                        
                    except Exception as e:
                        logger.error(f"Authentication failed for user {user_id}: {e}")
                        await websocket.send_text(json.dumps({
                            "type": "authentication_failed",
                            "error": "Invalid token"
                        }))
                        
                elif message_type == "heartbeat":
                    # Handle heartbeat
                    if user_id:
                        await online_status_manager.update_heartbeat(user_id, db)
                        await websocket.send_text(json.dumps({
                            "type": "heartbeat_ack",
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Not authenticated"
                        }))
                        
                elif message_type == "status_update":
                    # Handle manual status updates
                    if user_id:
                        status = message.get("status", "online")
                        if status == "online":
                            await online_status_manager.set_user_online(user_id, db)
                        elif status == "offline":
                            await online_status_manager.set_user_offline(user_id, db)
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "Not authenticated"
                        }))
                        
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from connection {connection_id}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format"
                }))
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error for connection {connection_id}: {e}")
    finally:
        await online_status_manager.disconnect(connection_id, db)

# REST API endpoints

@router.get("/users")
async def get_online_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get list of currently online users"""
    try:
        online_users = await online_status_manager.get_online_users(db)
        return {
            "online_users": online_users,
            "total_count": len(online_users)
        }
    except Exception as e:
        logger.error(f"Error fetching online users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch online users"
        )

@router.get("/shops/{shop_id}")
async def get_shop_online_status(
    shop_id: str,
    db: Session = Depends(get_db)
):
    """Get online status for a specific shop (public endpoint)"""
    try:
        status_data = await online_status_manager.get_shop_online_status(shop_id, db)
        return status_data
    except Exception as e:
        logger.error(f"Error fetching shop online status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch shop online status"
        )

@router.post("/update")
async def update_online_status(
    status_data: OnlineStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's online status"""
    try:
        if status_data.status == "online":
            await online_status_manager.set_user_online(current_user.id, db)
        elif status_data.status == "offline":
            await online_status_manager.set_user_offline(current_user.id, db)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid status. Must be 'online' or 'offline'"
            )
            
        return {"success": True, "message": f"Status updated to {status_data.status}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating online status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update online status"
        )

@router.post("/heartbeat")
async def send_heartbeat(
    heartbeat_data: HeartbeatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Receive heartbeat from shop owners"""
    try:
        await online_status_manager.update_heartbeat(current_user.id, db)
        return {
            "success": True,
            "message": "Heartbeat received",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error processing heartbeat: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process heartbeat"
        )

@router.get("/shops")
async def get_online_shops(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get list of shops with online owners (public endpoint)"""
    try:
        if limit > 100:
            limit = 100  # Prevent excessive queries
            
        online_shops = await online_status_manager.get_online_shops(limit, db)
        return {
            "shops": online_shops,
            "total_count": len(online_shops),
            "limit": limit
        }
    except Exception as e:
        logger.error(f"Error fetching online shops: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch online shops"
        )

@router.get("/status/{user_id}")
async def get_user_online_status(
    user_id: str,
    db: Session = Depends(get_db)
):
    """Get online status for a specific user (public endpoint)"""
    try:
        online_status = db.query(OnlineStatus).filter(OnlineStatus.user_id == user_id).first()
        
        if not online_status:
            return {
                "user_id": user_id,
                "is_online": False,
                "last_seen": None,
                "status_type": "offline"
            }
            
        return {
            "user_id": user_id,
            "is_online": online_status.is_online,
            "last_seen": online_status.last_seen.isoformat() if online_status.last_seen else None,
            "status_type": online_status.status_type,
            "last_heartbeat": online_status.last_heartbeat.isoformat() if online_status.last_heartbeat else None
        }
        
    except Exception as e:
        logger.error(f"Error fetching user online status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user online status"
        )

@router.get("/stats")
async def get_online_status_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get online status statistics (admin endpoint)"""
    try:
        # Check if user is admin
        if current_user.role.value != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
            
        # Get statistics
        total_online = db.query(OnlineStatus).filter(OnlineStatus.is_online == True).count()
        total_registered = db.query(User).count()
        shop_owners_online = db.query(OnlineStatus).join(User).filter(
            OnlineStatus.is_online == True,
            User.role == "SHOP_OWNER"
        ).count()
        
        return {
            "total_users_online": total_online,
            "total_registered_users": total_registered,
            "shop_owners_online": shop_owners_online,
            "active_connections": len(online_status_manager.active_connections),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching online status stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch online status statistics"
        )