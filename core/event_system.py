"""
Event System for IziShop Role Upgrade System
Implements event-driven architecture based on tech giant best practices
"""

from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4
import asyncio
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class EventType(str, Enum):
    """Enumeration of all system events"""
    ROLE_UPGRADED = "role.upgraded"
    ROLE_UPGRADE_FAILED = "role.upgrade_failed"
    SHOP_CREATED = "shop.created"
    NOTIFICATION_CREATED = "notification.created"
    AUDIT_LOG_CREATED = "audit.log_created"
    ORDER_STATUS_CHANGED = "order.status_changed"
    ORDER_CREATED = "order.created"
    ORDER_CANCELLED = "order.cancelled"

@dataclass
class EventMetadata:
    """Metadata for events"""
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SystemEvent:
    """Base system event"""
    event_id: UUID = field(default_factory=uuid4)
    event_type: EventType = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    data: Dict[str, Any] = field(default_factory=dict)
    metadata: EventMetadata = field(default_factory=EventMetadata)
    source: str = "system"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary"""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type.value if self.event_type else None,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "metadata": {
                "ip_address": self.metadata.ip_address,
                "user_agent": self.metadata.user_agent,
                "session_id": self.metadata.session_id,
                "request_id": self.metadata.request_id,
                "additional_data": self.metadata.additional_data
            },
            "source": self.source
        }

@dataclass
class RoleUpgradeEvent(SystemEvent):
    """Specific event for role upgrades"""
    def __init__(
        self,
        user_id: UUID,
        old_role: str,
        new_role: str,
        trigger_source: str,
        triggered_by: Optional[UUID] = None,
        metadata: Optional[EventMetadata] = None
    ):
        super().__init__(
            event_type=EventType.ROLE_UPGRADED,
            data={
                "user_id": str(user_id),
                "old_role": old_role,
                "new_role": new_role,
                "trigger_source": trigger_source,
                "triggered_by": str(triggered_by) if triggered_by else None
            },
            metadata=metadata or EventMetadata(),
            source="role_manager"
        )

@dataclass
class OrderStatusChangeEvent(SystemEvent):
    """Specific event for order status changes"""
    def __init__(
        self,
        order_id: str,
        customer_id: str,
        old_status: str,
        new_status: str,
        changed_by: Optional[str] = None,
        notes: Optional[str] = None,
        estimated_delivery: Optional[str] = None,
        metadata: Optional[EventMetadata] = None
    ):
        super().__init__(
            event_type=EventType.ORDER_STATUS_CHANGED,
            data={
                "order_id": order_id,
                "customer_id": customer_id,
                "old_status": old_status,
                "new_status": new_status,
                "changed_by": changed_by,
                "notes": notes,
                "estimated_delivery": estimated_delivery,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            metadata=metadata or EventMetadata(),
            source="order_service"
        )

class EventBus:
    """Central event bus for the system"""
    
    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._middleware: List[Callable] = []
        self._event_queue: asyncio.Queue = None
        self._processing_task: Optional[asyncio.Task] = None
        self._is_running = False
    
    async def initialize(self):
        """Initialize the event bus"""
        if not self._event_queue:
            self._event_queue = asyncio.Queue()
        
        if not self._processing_task and not self._is_running:
            self._processing_task = asyncio.create_task(self._process_events())
            self._is_running = True
            logger.info("EventBus initialized and processing started")
    
    def register_handler(self, event_type: EventType, handler: Callable):
        """Register an event handler"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        self._handlers[event_type].append(handler)
        logger.info(f"Registered handler for {event_type.value}")
    
    def add_middleware(self, middleware: Callable):
        """Add middleware for event processing"""
        self._middleware.append(middleware)
        logger.info(f"Added middleware: {middleware.__name__}")
    
    async def emit_event(self, event: SystemEvent):
        """Emit an event to the bus"""
        if not self._event_queue:
            await self.initialize()
        
        # Apply middleware
        for middleware in self._middleware:
            try:
                event = await middleware(event)
                if not event:  # Middleware can filter out events
                    return
            except Exception as e:
                logger.error(f"Middleware error: {e}")
                continue
        
        await self._event_queue.put(event)
        logger.debug(f"Event emitted: {event.event_type.value} - ID: {event.event_id}")
    
    async def _process_events(self):
        """Process events from the queue"""
        while self._is_running:
            try:
                # Wait for events with timeout to allow graceful shutdown
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Process the event
                await self._handle_event(event)
                self._event_queue.task_done()
                
            except Exception as e:
                logger.error(f"Event processing error: {e}")
    
    async def _handle_event(self, event: SystemEvent):
        """Handle a single event"""
        handlers = self._handlers.get(event.event_type, [])
        
        if not handlers:
            logger.warning(f"No handlers registered for event type: {event.event_type.value}")
            return
        
        # Execute all handlers concurrently
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(self._execute_handler(handler, event))
            tasks.append(task)
        
        if tasks:
            # Wait for all handlers to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Log any handler failures
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Handler {handlers[i].__name__} failed for event {event.event_id}: {result}")
    
    async def _execute_handler(self, handler: Callable, event: SystemEvent):
        """Execute a single event handler safely"""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
            logger.debug(f"Handler {handler.__name__} completed for event {event.event_id}")
        except Exception as e:
            logger.error(f"Handler {handler.__name__} error: {e}")
            raise
    
    async def shutdown(self):
        """Shutdown the event bus gracefully"""
        self._is_running = False
        
        if self._processing_task:
            await self._processing_task
            self._processing_task = None
        
        # Process remaining events
        if self._event_queue:
            while not self._event_queue.empty():
                try:
                    event = self._event_queue.get_nowait()
                    await self._handle_event(event)
                    self._event_queue.task_done()
                except asyncio.QueueEmpty:
                    break
        
        logger.info("EventBus shutdown completed")

# Global event bus instance
event_bus = EventBus()

# Decorator for registering event handlers
def event_handler(event_type: EventType):
    """Decorator to register event handlers"""
    def decorator(func):
        event_bus.register_handler(event_type, func)
        return func
    return decorator

# Middleware for logging events
async def logging_middleware(event: SystemEvent) -> SystemEvent:
    """Log all events for debugging"""
    logger.info(f"Event: {event.event_type.value} - User: {event.data.get('user_id', 'N/A')} - Source: {event.source}")
    return event

# Middleware for audit trail
async def audit_middleware(event: SystemEvent) -> SystemEvent:
    """Create audit logs for important events"""
    # This will be connected to the audit service later
    if event.event_type in [EventType.ROLE_UPGRADED, EventType.SHOP_CREATED, EventType.ORDER_STATUS_CHANGED, EventType.ORDER_CANCELLED]:
        logger.info(f"Audit required for event: {event.event_type.value}")
    return event

# Initialize middleware
event_bus.add_middleware(logging_middleware)
event_bus.add_middleware(audit_middleware)