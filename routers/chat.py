from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.connection import get_db
from schemas.user import UserResponse
from routers.auth import get_current_user
from models.chat import (
    Conversation, Message, ConversationParticipant, SupportTicket,
    ConversationType, MessageStatus
)
from models.contacts import Contact, ContactStatus, UserStatus, BlockedUser
from models.user import User
from models.shop import Shop
from models.order import Order
from models.product import Product
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import json
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Utility function to format datetime as UTC ISO string
def format_utc_timestamp(dt: datetime) -> str:
    """Format datetime as UTC ISO string with Z suffix"""
    if dt is None:
        return None
    # Ensure the datetime is treated as UTC
    if dt.tzinfo is None:
        # Assume naive datetime is UTC (as SQLite stores it)
        return dt.isoformat() + 'Z'
    return dt.isoformat()

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, List[str]] = {}

    async def connect(self, websocket: WebSocket, user_id: str, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket

        if user_id not in self.user_connections:
            self.user_connections[user_id] = []
        self.user_connections[user_id].append(connection_id)

        logger.info(f"User {user_id} connected with connection {connection_id}")

    def disconnect(self, user_id: str, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        if user_id in self.user_connections:
            if connection_id in self.user_connections[user_id]:
                self.user_connections[user_id].remove(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        logger.info(f"User {user_id} disconnected from connection {connection_id}")

    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.user_connections:
            for connection_id in self.user_connections[user_id]:
                if connection_id in self.active_connections:
                    try:
                        await self.active_connections[connection_id].send_text(json.dumps(message))
                    except Exception as e:
                        logger.error(f"Error sending message to {connection_id}: {e}")
                        self.disconnect(user_id, connection_id)

    async def broadcast_to_conversation(self, message: dict, conversation_id: str, exclude_user: str = None):
        # Get all participants in the conversation
        # This would need database access to get participants
        pass

manager = ConnectionManager()

# Pydantic models for requests/responses
class ConversationCreate(BaseModel):
    type: str
    title: Optional[str] = None
    participant_ids: Optional[List[str]] = None  # For direct messages and group chats
    group_name: Optional[str] = None
    group_description: Optional[str] = None
    shop_id: Optional[str] = None
    order_id: Optional[str] = None
    product_id: Optional[str] = None
    initial_message: Optional[str] = None

class DirectMessageCreate(BaseModel):
    recipient_id: str
    initial_message: str

class GroupChatCreate(BaseModel):
    group_name: str
    participant_ids: List[str]
    group_description: Optional[str] = None
    initial_message: Optional[str] = None

class ContactRequest(BaseModel):
    user_id: str
    message: Optional[str] = None

class UserSearchResult(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: Optional[str]
    avatar: Optional[str]
    is_online: bool
    last_seen: Optional[datetime]
    is_contact: bool
    contact_status: Optional[str]

class MessageCreate(BaseModel):
    content: str
    message_type: str = "text"
    reply_to_id: Optional[str] = None

class ConversationResponse(BaseModel):
    id: str
    type: str
    title: Optional[str]
    is_active: bool
    unread_count: int
    last_message: Optional[Dict[str, Any]]
    last_message_at: datetime
    participants: List[Dict[str, Any]]
    context: Optional[Dict[str, Any]]

class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    sender_name: str
    sender_avatar: Optional[str]
    content: str
    message_type: str
    status: str
    is_bot_message: bool
    created_at: datetime
    read_at: Optional[datetime]
    reply_to: Optional[Dict[str, Any]]
    attachments: Optional[List[Dict[str, Any]]]

# AI Bot responses for common queries
class ChatBot:
    @staticmethod
    def generate_response(message_content: str, context: Dict[str, Any] = None) -> tuple[str, bool]:
        """Generate bot response. Returns (response, needs_human_escalation)"""
        content_lower = message_content.lower()

        # Order-related queries
        if any(word in content_lower for word in ['order', 'delivery', 'shipping', 'tracking']):
            if context and context.get('order_id'):
                return ("I can see you're asking about your order. Let me check the status for you. Based on our records, your order is currently being processed. A human agent will assist you with detailed tracking information.", False)
            return ("I'd be happy to help with your order inquiry. Could you please provide your order number?", False)

        # Payment queries
        if any(word in content_lower for word in ['payment', 'refund', 'billing', 'charge']):
            return ("I understand you have a payment-related question. For security reasons, I'll connect you with a human agent who can securely access your payment information.", True)

        # Product queries
        if any(word in content_lower for word in ['product', 'item', 'price', 'stock', 'availability']):
            return ("I can help you with product information. What specific details would you like to know about our products?", False)

        # Account issues
        if any(word in content_lower for word in ['account', 'login', 'password', 'access']):
            return ("For account security, I'll connect you with a support agent who can help you with account-related issues.", True)

        # General greeting
        if any(word in content_lower for word in ['hello', 'hi', 'help', 'support']):
            return ("Hello! I'm here to help you. What can I assist you with today?", False)

        # Default response
        return ("I understand your message. Let me connect you with a human agent who can provide the best assistance for your specific needs.", True)

# WebSocket endpoint for real-time chat
@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(...),
    db: Session = Depends(get_db)
):
    # Validate token (simplified - you should use proper JWT validation)
    connection_id = str(uuid.uuid4())

    try:
        await manager.connect(websocket, user_id, connection_id)

        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)

            # Handle different message types
            if message_data['type'] == 'send_message':
                await handle_send_message(message_data, user_id, db)
            elif message_data['type'] == 'mark_read':
                await handle_mark_read(message_data, user_id, db)
            elif message_data['type'] == 'typing':
                await handle_typing_indicator(message_data, user_id)

    except WebSocketDisconnect:
        manager.disconnect(user_id, connection_id)
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
        manager.disconnect(user_id, connection_id)

async def handle_send_message(message_data: dict, user_id: str, db: Session):
    """Handle sending a new message"""
    try:
        conversation_id = message_data['conversation_id']
        content = message_data['content']

        # Create message in database
        message = Message(
            conversation_id=conversation_id,
            sender_id=user_id,
            content=content,
            message_type=message_data.get('message_type', 'text'),
            status=MessageStatus.SENT
        )
        db.add(message)

        # Update conversation timestamp
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation:
            conversation.last_message_at = datetime.utcnow()

        db.commit()

        # Send to all participants
        await notify_conversation_participants(conversation_id, {
            'type': 'new_message',
            'message': {
                'id': message.id,
                'conversation_id': conversation_id,
                'sender_id': user_id,
                'content': content,
                'created_at': format_utc_timestamp(message.created_at),
                'message_type': message.message_type
            }
        }, exclude_user=user_id, db=db)

        # Generate bot response if applicable
        if conversation and conversation.type == ConversationType.CUSTOMER_SUPPORT:
            await generate_bot_response(conversation, message, db)

    except Exception as e:
        logger.error(f"Error handling send message: {e}")

async def handle_mark_read(message_data: dict, user_id: str, db: Session):
    """Handle marking messages as read"""
    try:
        conversation_id = message_data['conversation_id']
        message_id = message_data.get('message_id')

        # Update participant's last read message
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == user_id
        ).first()

        if participant:
            participant.last_read_message_id = message_id
            participant.unread_count = 0
            participant.last_seen_at = datetime.utcnow()
            db.commit()

    except Exception as e:
        logger.error(f"Error handling mark read: {e}")

async def handle_typing_indicator(message_data: dict, user_id: str):
    """Handle typing indicator"""
    conversation_id = message_data['conversation_id']
    is_typing = message_data['is_typing']

    # Broadcast typing indicator to other participants
    await manager.broadcast_to_conversation({
        'type': 'typing_indicator',
        'conversation_id': conversation_id,
        'user_id': user_id,
        'is_typing': is_typing
    }, conversation_id, exclude_user=user_id)

async def generate_bot_response(conversation: Conversation, user_message: Message, db: Session):
    """Generate and send bot response"""
    try:
        # Prepare context
        context = {}
        if conversation.order_id:
            context['order_id'] = conversation.order_id
        if conversation.product_id:
            context['product_id'] = conversation.product_id

        # Generate response
        bot_response, needs_escalation = ChatBot.generate_response(user_message.content, context)

        # Create bot message
        bot_message = Message(
            conversation_id=conversation.id,
            sender_id="system",  # System user for bot
            content=bot_response,
            message_type="text",
            is_bot_message=True,
            requires_human_escalation=needs_escalation,
            status=MessageStatus.DELIVERED
        )
        db.add(bot_message)

        # Escalate if needed
        if needs_escalation:
            conversation.is_escalated = True
            conversation.priority = "high"

        db.commit()

        # Send bot response to user
        await manager.send_personal_message({
            'type': 'new_message',
            'message': {
                'id': bot_message.id,
                'conversation_id': conversation.id,
                'sender_id': "system",
                'sender_name': "IziShop Assistant",
                'content': bot_response,
                'created_at': format_utc_timestamp(bot_message.created_at),
                'is_bot_message': True,
                'message_type': 'text'
            }
        }, user_message.sender_id)

    except Exception as e:
        logger.error(f"Error generating bot response: {e}")

async def notify_conversation_participants(conversation_id: str, message: dict, exclude_user: str = None, db: Session = None):
    """Notify all participants in a conversation"""
    try:
        participants = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.is_active == True
        ).all()

        for participant in participants:
            if participant.user_id != exclude_user:
                await manager.send_personal_message(message, participant.user_id)

    except Exception as e:
        logger.error(f"Error notifying participants: {e}")

# REST API endpoints
@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    conversation_data: ConversationCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new conversation"""
    try:
        # Create conversation
        conversation = Conversation(
            type=ConversationType(conversation_data.type),
            title=conversation_data.title,
            customer_id=current_user.id,
            shop_id=conversation_data.shop_id,
            order_id=conversation_data.order_id,
            product_id=conversation_data.product_id
        )
        db.add(conversation)
        db.flush()  # Get the ID

        # Add current user as participant
        participant = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=current_user.id
        )
        db.add(participant)

        # Add shop owner as participant if shop_id provided
        if conversation_data.shop_id:
            shop = db.query(Shop).filter(Shop.id == conversation_data.shop_id).first()
            if shop and shop.owner_id:
                shop_participant = ConversationParticipant(
                    conversation_id=conversation.id,
                    user_id=shop.owner_id
                )
                db.add(shop_participant)

        # Create initial message
        initial_message = Message(
            conversation_id=conversation.id,
            sender_id=current_user.id,
            content=conversation_data.initial_message,
            message_type="text",
            status=MessageStatus.SENT
        )
        db.add(initial_message)

        db.commit()

        # Generate bot response for customer support
        if conversation.type == ConversationType.CUSTOMER_SUPPORT:
            await generate_bot_response(conversation, initial_message, db)

        return format_conversation_response(conversation, current_user.id, db)

    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create conversation")

@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all conversations for the current user"""
    try:
        # Get conversations where user is a participant
        participants = db.query(ConversationParticipant).filter(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.is_active == True
        ).all()

        conversations = []
        for participant in participants:
            conversation = db.query(Conversation).filter(
                Conversation.id == participant.conversation_id,
                Conversation.is_active == True
            ).first()

            if conversation:
                conversations.append(format_conversation_response(conversation, current_user.id, db))

        # Sort by last message time
        conversations.sort(key=lambda x: x.last_message_at, reverse=True)

        return conversations

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversations")

@router.get("/conversations/{conversation_id}/messages", response_model=List[MessageResponse])
async def get_messages(
    conversation_id: str,
    skip: int = 0,
    limit: int = 50,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get messages for a conversation"""
    try:
        # Verify user is participant
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.is_active == True
        ).first()

        if not participant:
            raise HTTPException(status_code=403, detail="Access denied")

        # Get messages
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.is_deleted == False
        ).order_by(Message.created_at.desc()).offset(skip).limit(limit).all()

        # Format response
        formatted_messages = []
        for message in messages:
            sender = db.query(User).filter(User.id == message.sender_id).first()
            formatted_messages.append(format_message_response(message, sender))

        return formatted_messages

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        raise HTTPException(status_code=500, detail="Failed to get messages")

def format_conversation_response(conversation: Conversation, user_id: str, db: Session) -> ConversationResponse:
    """Format conversation for API response"""
    # Get unread count for user
    participant = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.user_id == user_id
    ).first()

    unread_count = participant.unread_count if participant else 0

    # Get last message
    last_message = db.query(Message).filter(
        Message.conversation_id == conversation.id,
        Message.is_deleted == False
    ).order_by(Message.created_at.desc()).first()

    last_message_data = None
    if last_message:
        sender = db.query(User).filter(User.id == last_message.sender_id).first()
        last_message_data = {
            'content': last_message.content,
            'sender_name': f"{sender.first_name} {sender.last_name}" if sender else "System",
            'created_at': format_utc_timestamp(last_message.created_at),
            'is_bot_message': last_message.is_bot_message
        }

    # Get participants
    participants_data = []
    participants = db.query(ConversationParticipant).filter(
        ConversationParticipant.conversation_id == conversation.id,
        ConversationParticipant.is_active == True
    ).all()

    for p in participants:
        user = db.query(User).filter(User.id == p.user_id).first()
        if user:
            participants_data.append({
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'avatar': getattr(user, 'avatar', None),
                'last_seen': format_utc_timestamp(p.last_seen_at)
            })

    # Context data
    context = {}
    if conversation.order_id:
        order = db.query(Order).filter(Order.id == conversation.order_id).first()
        if order:
            context['order'] = {
                'id': order.id,
                'total': float(order.total_amount),
                'status': order.status
            }

    if conversation.product_id:
        product = db.query(Product).filter(Product.id == conversation.product_id).first()
        if product:
            context['product'] = {
                'id': product.id,
                'name': product.name,
                'price': float(product.price)
            }

    return ConversationResponse(
        id=conversation.id,
        type=conversation.type.value,
        title=conversation.title or get_conversation_title(conversation, user_id, db),
        is_active=conversation.is_active,
        unread_count=unread_count,
        last_message=last_message_data,
        last_message_at=conversation.last_message_at,
        participants=participants_data,
        context=context if context else None
    )

def format_message_response(message: Message, sender: User) -> MessageResponse:
    """Format message for API response"""
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=f"{sender.first_name} {sender.last_name}" if sender else "System",
        sender_avatar=getattr(sender, 'avatar', None) if sender else None,
        content=message.content,
        message_type=message.message_type,
        status=message.status.value,
        is_bot_message=message.is_bot_message,
        created_at=message.created_at,
        read_at=message.read_at,
        reply_to=None,  # TODO: implement reply_to formatting
        attachments=None  # TODO: implement attachments
    )

# User discovery and contact management endpoints
@router.get("/users/search", response_model=List[UserSearchResult])
async def search_users(
    query: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, le=50),
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search for users on the platform"""
    try:
        # Search users by name or email
        users = db.query(User).filter(
            User.id != current_user.id,  # Exclude current user
            User.is_active == True,
            (User.first_name.ilike(f"%{query}%") |
             User.last_name.ilike(f"%{query}%") |
             User.email.ilike(f"%{query}%"))
        ).limit(limit).all()

        # Get contact relationships
        contacts = db.query(Contact).filter(
            (Contact.requester_id == current_user.id) |
            (Contact.addressee_id == current_user.id)
        ).all()

        contact_map = {}
        for contact in contacts:
            other_user_id = contact.addressee_id if contact.requester_id == current_user.id else contact.requester_id
            contact_map[other_user_id] = contact.status.value

        # Get user statuses
        user_statuses = db.query(UserStatus).filter(
            UserStatus.user_id.in_([u.id for u in users])
        ).all()
        status_map = {status.user_id: status for status in user_statuses}

        # Format results
        results = []
        for user in users:
            status = status_map.get(user.id)
            results.append(UserSearchResult(
                id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email if user.email else None,
                avatar=getattr(user, 'avatar', None),
                is_online=status.is_online if status else False,
                last_seen=status.last_seen if status else None,
                is_contact=user.id in contact_map,
                contact_status=contact_map.get(user.id)
            ))

        return results

    except Exception as e:
        logger.error(f"Error searching users: {e}")
        raise HTTPException(status_code=500, detail="Failed to search users")

@router.post("/contacts/request")
async def send_contact_request(
    request_data: ContactRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a contact request to another user"""
    try:
        # Check if users are already contacts
        existing_contact = db.query(Contact).filter(
            ((Contact.requester_id == current_user.id) & (Contact.addressee_id == request_data.user_id)) |
            ((Contact.requester_id == request_data.user_id) & (Contact.addressee_id == current_user.id))
        ).first()

        if existing_contact:
            raise HTTPException(status_code=400, detail="Contact relationship already exists")

        # Create contact request
        contact = Contact(
            requester_id=current_user.id,
            addressee_id=request_data.user_id,
            status=ContactStatus.PENDING
        )
        db.add(contact)
        db.commit()

        return {"message": "Contact request sent successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending contact request: {e}")
        raise HTTPException(status_code=500, detail="Failed to send contact request")

@router.post("/contacts/{contact_id}/accept")
async def accept_contact_request(
    contact_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept a contact request"""
    try:
        contact = db.query(Contact).filter(
            Contact.id == contact_id,
            Contact.addressee_id == current_user.id,
            Contact.status == ContactStatus.PENDING
        ).first()

        if not contact:
            raise HTTPException(status_code=404, detail="Contact request not found")

        contact.status = ContactStatus.ACCEPTED
        contact.accepted_at = datetime.utcnow()
        db.commit()

        return {"message": "Contact request accepted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error accepting contact request: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept contact request")

@router.get("/contacts")
async def get_contacts(
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's contacts"""
    try:
        contacts = db.query(Contact).filter(
            ((Contact.requester_id == current_user.id) | (Contact.addressee_id == current_user.id)),
            Contact.status == ContactStatus.ACCEPTED
        ).all()

        results = []
        for contact in contacts:
            other_user_id = contact.addressee_id if contact.requester_id == current_user.id else contact.requester_id
            other_user = db.query(User).filter(User.id == other_user_id).first()

            if other_user:
                # Get user status
                status = db.query(UserStatus).filter(UserStatus.user_id == other_user.id).first()

                results.append({
                    'id': other_user.id,
                    'name': f"{other_user.first_name} {other_user.last_name}",
                    'avatar': getattr(other_user, 'avatar', None),
                    'is_online': status.is_online if status else False,
                    'last_seen': status.last_seen if status else None,
                    'nickname': contact.nickname,
                    'is_favorite': contact.is_favorite
                })

        return results

    except Exception as e:
        logger.error(f"Error getting contacts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get contacts")

@router.post("/conversations/direct", response_model=ConversationResponse)
async def create_direct_conversation(
    conversation_data: DirectMessageCreate,
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a direct message conversation"""
    try:
        # Validate recipient exists
        from models.user import User
        recipient = db.query(User).filter(User.id == conversation_data.recipient_id).first()
        if not recipient:
            logger.warning(f"Recipient not found: {conversation_data.recipient_id}")
            raise HTTPException(status_code=404, detail=f"Recipient user not found: {conversation_data.recipient_id}")

        # Check if user is trying to message themselves
        if current_user.id == conversation_data.recipient_id:
            raise HTTPException(status_code=400, detail="Cannot create conversation with yourself")

        # Check if conversation already exists
        existing = db.query(Conversation).join(ConversationParticipant).filter(
            Conversation.type == ConversationType.DIRECT_MESSAGE,
            ConversationParticipant.user_id.in_([current_user.id, conversation_data.recipient_id])
        ).group_by(Conversation.id).having(
            func.count(ConversationParticipant.user_id) == 2
        ).first()

        if existing:
            logger.info(f"Found existing conversation: {existing.id}")

            # If there's an initial message, add it to the existing conversation
            if conversation_data.initial_message:
                # Create new message
                new_message = Message(
                    conversation_id=existing.id,
                    sender_id=current_user.id,
                    content=conversation_data.initial_message,
                    message_type="text",
                    status=MessageStatus.SENT
                )
                db.add(new_message)

                # Update conversation timestamp
                existing.last_message_at = datetime.utcnow()

                # Increment recipient's unread count
                recipient_participant = db.query(ConversationParticipant).filter(
                    ConversationParticipant.conversation_id == existing.id,
                    ConversationParticipant.user_id == conversation_data.recipient_id
                ).first()

                if recipient_participant:
                    recipient_participant.unread_count += 1

                db.commit()

                # Notify recipient via WebSocket
                background_tasks.add_task(
                    notify_conversation_participants,
                    existing.id,
                    {
                        'type': 'new_message',
                        'message': {
                            'id': new_message.id,
                            'conversation_id': existing.id,
                            'sender_id': current_user.id,
                            'content': conversation_data.initial_message,
                            'created_at': format_utc_timestamp(new_message.created_at),
                            'message_type': 'text'
                        }
                    },
                    current_user.id,  # exclude_user
                    db
                )

            return format_conversation_response(existing, current_user.id, db)

        # Create new conversation
        conversation = Conversation(
            type=ConversationType.DIRECT_MESSAGE,
            created_by=current_user.id
        )
        db.add(conversation)
        db.flush()

        # Send initial message first to determine unread counts
        initial_message = None
        if conversation_data.initial_message:
            initial_message = Message(
                conversation_id=conversation.id,
                sender_id=current_user.id,
                content=conversation_data.initial_message,
                message_type="text",
                status=MessageStatus.SENT
            )
            db.add(initial_message)
            db.flush()  # Flush to get the message ID

        # Add participants with correct unread counts
        # Current user has read the initial message (they sent it), recipient hasn't
        participants = [
            ConversationParticipant(
                conversation_id=conversation.id,
                user_id=current_user.id,
                unread_count=0,  # Sender has no unread messages
                last_seen_at=datetime.utcnow() if conversation_data.initial_message else None
            ),
            ConversationParticipant(
                conversation_id=conversation.id,
                user_id=conversation_data.recipient_id,
                unread_count=1 if conversation_data.initial_message else 0,  # Recipient has 1 unread if there's an initial message
                last_seen_at=None  # Recipient hasn't seen the conversation yet
            )
        ]
        db.add_all(participants)

        db.commit()

        # Notify recipient via WebSocket if initial message was sent
        if conversation_data.initial_message and initial_message:
            # Schedule notification as background task to avoid blocking response
            background_tasks.add_task(
                notify_conversation_participants,
                conversation.id,
                {
                    'type': 'new_message',
                    'message': {
                        'id': initial_message.id,
                        'conversation_id': conversation.id,
                        'sender_id': current_user.id,
                        'content': conversation_data.initial_message,
                        'created_at': format_utc_timestamp(initial_message.created_at),
                        'message_type': 'text'
                    }
                },
                current_user.id,  # exclude_user
                db
            )

        logger.info(f"Created new direct conversation: {conversation.id} between {current_user.id} and {conversation_data.recipient_id}")
        return format_conversation_response(conversation, current_user.id, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating direct conversation: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {str(e)}")

@router.post("/conversations/group", response_model=ConversationResponse)
async def create_group_conversation(
    conversation_data: GroupChatCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a group chat conversation"""
    try:
        # Create group conversation
        conversation = Conversation(
            type=ConversationType.GROUP_CHAT,
            created_by=current_user.id,
            group_name=conversation_data.group_name,
            group_description=conversation_data.group_description
        )
        db.add(conversation)
        db.flush()

        # Add creator as admin
        creator_participant = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=current_user.id,
            is_admin=True,
            can_add_members=True,
            can_edit_group=True
        )
        db.add(creator_participant)

        # Add other participants
        for participant_id in conversation_data.participant_ids:
            if participant_id != current_user.id:  # Don't add creator twice
                participant = ConversationParticipant(
                    conversation_id=conversation.id,
                    user_id=participant_id
                )
                db.add(participant)

        # Send initial message
        if conversation_data.initial_message:
            initial_message = Message(
                conversation_id=conversation.id,
                sender_id=current_user.id,
                content=conversation_data.initial_message,
                message_type="text",
                status=MessageStatus.SENT
            )
            db.add(initial_message)

        db.commit()

        return format_conversation_response(conversation, current_user.id, db)

    except Exception as e:
        logger.error(f"Error creating group conversation: {e}")
        raise HTTPException(status_code=500, detail="Failed to create group conversation")

def get_conversation_title(conversation: Conversation, user_id: str, db: Session) -> str:
    """Generate conversation title based on context"""
    if conversation.type == ConversationType.GROUP_CHAT:
        return conversation.group_name or "Group Chat"
    elif conversation.type == ConversationType.CUSTOMER_SUPPORT:
        return "Customer Support"
    elif conversation.type == ConversationType.SHOP_CUSTOMER and conversation.shop:
        return f"Chat with {conversation.shop.name}"
    elif conversation.type == ConversationType.DIRECT_MESSAGE:
        # Get other participant's name
        participant = db.query(ConversationParticipant).filter(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.user_id != user_id,
            ConversationParticipant.is_active == True
        ).first()

        if participant:
            other_user = db.query(User).filter(User.id == participant.user_id).first()
            if other_user:
                return f"{other_user.first_name} {other_user.last_name}"

    return "Chat"