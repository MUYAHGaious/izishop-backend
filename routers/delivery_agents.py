"""
Delivery Agent Management System
Uber-inspired gig economy model for delivery services
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func
from database.connection import get_db
from services.auth import get_current_user
from models.user import User
from models.delivery_agent import DeliveryAgent
from models.delivery_assignment import DeliveryAssignment
from models.order import Order
from decimal import Decimal
import uuid

router = APIRouter(prefix="/api/delivery-agents", tags=["delivery-agents"])
logger = logging.getLogger(__name__)

# Constants
BASE_DELIVERY_FEE = Decimal('5.00')  # Base delivery fee
PLATFORM_CUT = Decimal('0.10')  # 10% platform fee
DISTANCE_RATE = Decimal('1.50')  # $1.50 per km

@router.post("/register")
async def register_as_delivery_agent(
    agent_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Register user as delivery agent with vehicle and availability info"""
    try:
        # Check if user can become delivery agent
        if current_user.role not in ['CUSTOMER', 'CASUAL_SELLER', 'DELIVERY_AGENT']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Shop owners cannot become delivery agents"
            )
        
        # Check if already registered as delivery agent
        existing_agent = db.query(DeliveryAgent).filter(
            DeliveryAgent.agent_id == current_user.id
        ).first()
        
        if existing_agent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already registered as delivery agent"
            )
        
        # Create delivery agent profile
        delivery_agent = DeliveryAgent(
            id=str(uuid.uuid4()),
            agent_id=current_user.id,
            vehicle_type=agent_data.get('vehicle_type', 'car'),
            license_plate=agent_data.get('license_plate', ''),
            phone_number=agent_data.get('phone_number', current_user.phone or ''),
            emergency_contact=agent_data.get('emergency_contact', ''),
            service_areas=agent_data.get('service_areas', []),
            availability_schedule=agent_data.get('availability_schedule', {}),
            is_active=True,
            is_available=False,  # Starts offline
            current_location=None,
            rating=5.0,  # Start with perfect rating
            total_deliveries=0,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(delivery_agent)
        
        # Update user role
        current_user.role = 'DELIVERY_AGENT'
        current_user.role_upgraded_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(delivery_agent)
        
        logger.info(f"User {current_user.id} registered as delivery agent")
        
        return {
            "message": "Successfully registered as delivery agent",
            "agent_id": delivery_agent.id,
            "status": "active",
            "vehicle_type": delivery_agent.vehicle_type
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error registering delivery agent: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register as delivery agent"
        )

@router.get("/profile")
async def get_agent_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get delivery agent profile"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can access this endpoint"
        )
    
    agent = db.query(DeliveryAgent).filter(
        DeliveryAgent.agent_id == current_user.id
    ).first()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery agent profile not found"
        )
    
    return {
        "id": agent.id,
        "vehicle_type": agent.vehicle_type,
        "license_plate": agent.license_plate,
        "phone_number": agent.phone_number,
        "service_areas": agent.service_areas,
        "availability_schedule": agent.availability_schedule,
        "is_available": agent.is_available,
        "rating": float(agent.rating),
        "total_deliveries": agent.total_deliveries,
        "current_location": agent.current_location,
        "created_at": agent.created_at.isoformat()
    }

@router.put("/availability")
async def toggle_availability(
    is_available: bool,
    current_location: Optional[dict] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Toggle delivery agent availability (go online/offline)"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can toggle availability"
        )
    
    agent = db.query(DeliveryAgent).filter(
        DeliveryAgent.agent_id == current_user.id
    ).first()
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery agent profile not found"
        )
    
    agent.is_available = is_available
    if current_location:
        agent.current_location = current_location
    
    if is_available:
        agent.last_seen_at = datetime.now(timezone.utc)
    
    db.commit()
    
    status_text = "online" if is_available else "offline"
    logger.info(f"Delivery agent {agent.id} went {status_text}")
    
    return {
        "message": f"Successfully went {status_text}",
        "is_available": is_available,
        "current_location": agent.current_location
    }

@router.get("/available-deliveries")
async def get_available_deliveries(
    max_distance: Optional[float] = 10.0,  # 10km radius
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get available delivery requests for the agent"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can view available deliveries"
        )
    
    agent = db.query(DeliveryAgent).filter(
        DeliveryAgent.agent_id == current_user.id
    ).first()
    
    if not agent or not agent.is_available:
        return {"deliveries": [], "message": "Agent is not available"}
    
    # Find unassigned delivery requests
    available_assignments = db.query(DeliveryAssignment).filter(
        and_(
            DeliveryAssignment.status == 'pending',
            DeliveryAssignment.assigned_agent_id.is_(None)
        )
    ).options(joinedload(DeliveryAssignment.order)).all()
    
    delivery_requests = []
    for assignment in available_assignments:
        # Calculate estimated earnings
        distance = assignment.estimated_distance or 5.0  # Default 5km
        base_fee = BASE_DELIVERY_FEE
        distance_fee = Decimal(str(distance)) * DISTANCE_RATE
        total_fee = base_fee + distance_fee
        agent_earning = total_fee * (1 - PLATFORM_CUT)
        
        delivery_requests.append({
            "assignment_id": assignment.id,
            "order_id": assignment.order_id,
            "pickup_location": assignment.pickup_location,
            "delivery_location": assignment.delivery_location,
            "estimated_distance": distance,
            "total_fee": float(total_fee),
            "agent_earning": float(agent_earning),
            "pickup_time": assignment.pickup_time.isoformat() if assignment.pickup_time else None,
            "delivery_deadline": assignment.delivery_deadline.isoformat() if assignment.delivery_deadline else None,
            "special_instructions": assignment.special_instructions,
            "created_at": assignment.created_at.isoformat()
        })
    
    return {
        "deliveries": delivery_requests,
        "total_available": len(delivery_requests),
        "agent_location": agent.current_location
    }

@router.post("/accept-delivery/{assignment_id}")
async def accept_delivery(
    assignment_id: str,
    estimated_arrival: Optional[int] = 15,  # minutes
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept a delivery assignment"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can accept deliveries"
        )
    
    # Get agent profile
    agent = db.query(DeliveryAgent).filter(
        DeliveryAgent.agent_id == current_user.id
    ).first()
    
    if not agent or not agent.is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Agent is not available for deliveries"
        )
    
    # Get the assignment
    assignment = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.id == assignment_id
    ).first()
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery assignment not found"
        )
    
    if assignment.assigned_agent_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery has already been accepted by another agent"
        )
    
    # Assign delivery to agent
    assignment.assigned_agent_id = current_user.id
    assignment.status = 'accepted'
    assignment.accepted_at = datetime.now(timezone.utc)
    assignment.estimated_pickup_time = datetime.now(timezone.utc) + timedelta(minutes=estimated_arrival)
    
    # Agent is now busy
    agent.is_available = False
    agent.current_assignment_id = assignment_id
    
    db.commit()
    db.refresh(assignment)
    
    logger.info(f"Delivery agent {agent.id} accepted assignment {assignment_id}")
    
    return {
        "message": "Delivery accepted successfully",
        "assignment_id": assignment_id,
        "status": "accepted",
        "estimated_pickup_time": assignment.estimated_pickup_time.isoformat(),
        "pickup_location": assignment.pickup_location,
        "delivery_location": assignment.delivery_location
    }

@router.post("/update-status/{assignment_id}")
async def update_delivery_status(
    assignment_id: str,
    new_status: str,
    location_update: Optional[dict] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update delivery status (picked_up, in_transit, delivered, etc.)"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can update delivery status"
        )
    
    valid_statuses = ['accepted', 'en_route_pickup', 'arrived_pickup', 'picked_up', 'in_transit', 'arrived_delivery', 'delivered', 'failed']
    
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Valid options: {', '.join(valid_statuses)}"
        )
    
    assignment = db.query(DeliveryAssignment).filter(
        and_(
            DeliveryAssignment.id == assignment_id,
            DeliveryAssignment.assigned_agent_id == current_user.id
        )
    ).first()
    
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found or not assigned to you"
        )
    
    # Update assignment status
    assignment.status = new_status
    assignment.updated_at = datetime.now(timezone.utc)
    
    if notes:
        assignment.agent_notes = notes
    
    # Update timestamps based on status
    if new_status == 'picked_up':
        assignment.picked_up_at = datetime.now(timezone.utc)
    elif new_status == 'delivered':
        assignment.delivered_at = datetime.now(timezone.utc)
        assignment.completion_time = datetime.now(timezone.utc)
        
        # Agent is now available again
        agent = db.query(DeliveryAgent).filter(
            DeliveryAgent.agent_id == current_user.id
        ).first()
        
        if agent:
            agent.is_available = True
            agent.current_assignment_id = None
            agent.total_deliveries += 1
    
    # Update agent location if provided
    if location_update:
        agent = db.query(DeliveryAgent).filter(
            DeliveryAgent.agent_id == current_user.id
        ).first()
        
        if agent:
            agent.current_location = location_update
            agent.last_seen_at = datetime.now(timezone.utc)
    
    db.commit()
    
    logger.info(f"Delivery {assignment_id} status updated to {new_status}")
    
    return {
        "message": f"Status updated to {new_status}",
        "assignment_id": assignment_id,
        "status": new_status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/my-deliveries")
async def get_my_deliveries(
    status_filter: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get delivery agent's delivery history"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can view delivery history"
        )
    
    query = db.query(DeliveryAssignment).filter(
        DeliveryAssignment.assigned_agent_id == current_user.id
    )
    
    if status_filter:
        query = query.filter(DeliveryAssignment.status == status_filter)
    
    assignments = query.order_by(desc(DeliveryAssignment.created_at)).offset(skip).limit(limit).all()
    
    deliveries = []
    for assignment in assignments:
        # Calculate earnings
        distance = assignment.estimated_distance or 5.0
        total_fee = BASE_DELIVERY_FEE + (Decimal(str(distance)) * DISTANCE_RATE)
        agent_earning = total_fee * (1 - PLATFORM_CUT)
        
        deliveries.append({
            "assignment_id": assignment.id,
            "order_id": assignment.order_id,
            "status": assignment.status,
            "pickup_location": assignment.pickup_location,
            "delivery_location": assignment.delivery_location,
            "distance": distance,
            "earnings": float(agent_earning),
            "accepted_at": assignment.accepted_at.isoformat() if assignment.accepted_at else None,
            "picked_up_at": assignment.picked_up_at.isoformat() if assignment.picked_up_at else None,
            "delivered_at": assignment.delivered_at.isoformat() if assignment.delivered_at else None,
            "created_at": assignment.created_at.isoformat()
        })
    
    return {
        "deliveries": deliveries,
        "total": len(deliveries)
    }

@router.get("/earnings-summary")
async def get_earnings_summary(
    period: str = Query("all_time", regex="^(today|week|month|all_time)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get delivery agent earnings summary"""
    if current_user.role != 'DELIVERY_AGENT':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only delivery agents can view earnings"
        )
    
    # Get date range based on period
    now = datetime.now(timezone.utc)
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    else:  # all_time
        start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    
    # Get completed deliveries in period
    query = db.query(DeliveryAssignment).filter(
        and_(
            DeliveryAssignment.assigned_agent_id == current_user.id,
            DeliveryAssignment.status == 'delivered',
            DeliveryAssignment.delivered_at >= start_date
        )
    )
    
    completed_deliveries = query.all()
    
    total_earnings = Decimal('0')
    total_deliveries = len(completed_deliveries)
    total_distance = 0.0
    
    for delivery in completed_deliveries:
        distance = delivery.estimated_distance or 5.0
        total_fee = BASE_DELIVERY_FEE + (Decimal(str(distance)) * DISTANCE_RATE)
        agent_earning = total_fee * (1 - PLATFORM_CUT)
        total_earnings += agent_earning
        total_distance += distance
    
    return {
        "period": period,
        "total_earnings": float(total_earnings),
        "total_deliveries": total_deliveries,
        "total_distance": total_distance,
        "average_earning_per_delivery": float(total_earnings / total_deliveries) if total_deliveries > 0 else 0,
        "platform_fee_rate": f"{float(PLATFORM_CUT * 100)}%"
    }