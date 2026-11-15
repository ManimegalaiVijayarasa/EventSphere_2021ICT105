import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.agents import agent_bus
from app.agents.base import Performative
from app.database import get_db
from app.models import (
    User, Venue, Event, TicketCategory, Booking, Ticket,
    VenueHire, MessageLog, AgentBelief
)
from app.schemas import (
    VenueCreate, VenueUpdate, VenueOut,
    EventCreate, EventUpdate, EventOut,
    VenueHireReviewRequest, AgentMessage
)
from app.security import get_admin_user

router = APIRouter(tags=["Admin Management"])
templates = Jinja2Templates(directory="app/templates")

# --- HTML Admin Views ---
@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard_page(
    request: Request,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    # Aggregated metrics
    total_events = db.query(Event).count()
    total_venues = db.query(Venue).count()
    total_bookings = db.query(Booking).filter(Booking.status == "confirmed").count()
    total_revenue = db.query(func.coalesce(func.sum(Booking.total_amount), 0.0)).filter(
        Booking.status == "confirmed"
    ).scalar()

    total_admitted = db.query(Ticket).filter(Ticket.status == "admitted").count()
    pending_hires = db.query(VenueHire).filter(VenueHire.status == "escalated").count()

    events = db.query(Event).order_by(Event.start_time.desc()).all()
    event_stats = []
    for ev in events:
        tickets_sold = db.query(func.coalesce(func.sum(Booking.quantity), 0)).filter(
            Booking.event_id == ev.id,
            Booking.status == "confirmed"
        ).scalar()

        ev_revenue = db.query(func.coalesce(func.sum(Booking.total_amount), 0.0)).filter(
            Booking.event_id == ev.id,
            Booking.status == "confirmed"
        ).scalar()

        checkins = db.query(Ticket).join(Booking).filter(
            Booking.event_id == ev.id,
            Ticket.status == "admitted"
        ).count()

        event_stats.append({
            "event": ev,
            "tickets_sold": tickets_sold,
            "revenue": ev_revenue,
            "checkins": checkins,
            "capacity": ev.venue.capacity if ev.venue else 0
        })

    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "user": user,
            "total_events": total_events,
            "total_venues": total_venues,
            "total_bookings": total_bookings,
            "total_revenue": round(total_revenue, 2),
            "total_admitted": total_admitted,
            "pending_hires": pending_hires,
            "event_stats": event_stats
        }
    )

@router.get("/admin/events", response_class=HTMLResponse)
def admin_events_page(
    request: Request,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    events = db.query(Event).order_by(Event.start_time.desc()).all()
    venues = db.query(Venue).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_events.html",
        context={
            "user": user,
            "events": events,
            "venues": venues
        }
    )

@router.get("/admin/venues", response_class=HTMLResponse)
def admin_venues_page(
    request: Request,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    venues = db.query(Venue).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_venues.html",
        context={
            "user": user,
            "venues": venues
        }
    )

@router.get("/admin/hires", response_class=HTMLResponse)
def admin_hires_page(
    request: Request,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    hires = db.query(VenueHire).order_by(VenueHire.created_at.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="admin_hire_requests.html",
        context={
            "user": user,
            "hires": hires
        }
    )

@router.get("/admin/agent-logs", response_class=HTMLResponse)
def admin_agent_logs_page(
    request: Request,
    conversation_id: Optional[str] = None,
    sender: Optional[str] = None,
    receiver: Optional[str] = None,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    query = db.query(MessageLog)
    if conversation_id:
        query = query.filter(MessageLog.conversation_id.ilike(f"%{conversation_id}%"))
    if sender:
        query = query.filter(MessageLog.sender == sender)
    if receiver:
        query = query.filter(MessageLog.receiver == receiver)

    logs = query.order_by(MessageLog.created_at.desc()).limit(150).all()
    distinct_convs = db.query(MessageLog.conversation_id).distinct().limit(25).all()

    return templates.TemplateResponse(
        request=request,
        name="admin_agent_logs.html",
        context={
            "user": user,
            "logs": logs,
            "conversations": [c[0] for c in distinct_convs],
            "filter_conv": conversation_id,
            "filter_sender": sender,
            "filter_receiver": receiver
        }
    )

# --- REST API Endpoints ---
@router.post("/api/admin/venues", response_model=VenueOut)
def create_venue_api(
    payload: VenueCreate,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    venue = Venue(
        name=payload.name.strip(),
        location=payload.location.strip(),
        capacity=payload.capacity,
        description=payload.description,
        image_url=payload.image_url,
        hourly_hire_rate=payload.hourly_hire_rate,
        is_open_for_hire=payload.is_open_for_hire
    )
    db.add(venue)
    db.commit()
    db.refresh(venue)
    return venue

@router.put("/api/admin/venues/{venue_id}", response_model=VenueOut)
def update_venue_api(
    venue_id: int,
    payload: VenueUpdate,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    venue = db.query(Venue).filter(Venue.id == venue_id).first()
    if not venue:
        raise HTTPException(status_code=404, detail="Venue not found")

    for key, value in payload.dict(exclude_unset=True).items():
        setattr(venue, key, value)

    db.commit()
    db.refresh(venue)
    return venue

@router.post("/api/admin/events", response_model=EventOut)
def create_event_api(
    payload: EventCreate,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    total_tickets = sum(cat.total_quantity for cat in payload.ticket_categories)

    # Multi-Agent Coordination: Check slot & capacity with VenueAgent
    conv_id = f"event-create-{uuid.uuid4().hex[:8]}"
    check_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="AdminUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_EVENT_SLOT",
            "venue_id": payload.venue_id,
            "start_time": payload.start_time.isoformat(),
            "end_time": payload.end_time.isoformat(),
            "total_tickets": total_tickets
        }
    )
    reply = agent_bus.send(check_msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "VenueAgent refused the event slot or capacity.")
        )

    # Slot approved by VenueAgent! Create Event and Ticket Categories
    event = Event(
        title=payload.title.strip(),
        category=payload.category,
        venue_id=payload.venue_id,
        start_time=payload.start_time,
        end_time=payload.end_time,
        description=payload.description,
        image_url=payload.image_url,
        status=payload.status or "draft"
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    for cat_data in payload.ticket_categories:
        cat = TicketCategory(
            event_id=event.id,
            name=cat_data.name.strip(),
            price=cat_data.price,
            total_quantity=cat_data.total_quantity,
            available_quantity=cat_data.total_quantity
        )
        db.add(cat)

    db.commit()
    db.refresh(event)
    return event

@router.post("/api/admin/events/{event_id}/publish")
def publish_event_api(
    event_id: int,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.status = "published"
    db.commit()
    return {"status": "published", "event_id": event.id}

@router.post("/api/admin/events/{event_id}/cancel")
def cancel_event_api(
    event_id: int,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    event.status = "cancelled"
    db.commit()

    # Delegate full refund processing to BookingAgent
    conv_id = f"cancel-ev-{uuid.uuid4().hex[:8]}"
    refund_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="AdminUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CANCEL_EVENT_REFUNDS",
            "event_id": event.id
        }
    )
    agent_bus.send(refund_msg, db=db)
    return {"status": "cancelled", "event_id": event.id, "refunds_issued": True}

@router.post("/api/admin/hires/review")
def review_hire_api(
    payload: VenueHireReviewRequest,
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    conv_id = f"hire-rev-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="AdminUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "ADMIN_REVIEW_HIRE",
            "hire_id": payload.hire_id,
            "decision": payload.decision,
            "admin_notes": payload.admin_notes
        }
    )
    reply = agent_bus.send(msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Hire review failed.")
        )
    return reply.content

@router.get("/api/admin/dashboard-stats")
def dashboard_stats_api(
    user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    # Sales per event for Chart.js
    events = db.query(Event).filter(Event.status.in_(["published", "cancelled"])).all()
    event_labels = []
    sales_data = []
    checkins_data = []

    for ev in events:
        event_labels.append(ev.title[:20])
        sold = db.query(func.coalesce(func.sum(Booking.quantity), 0)).filter(
            Booking.event_id == ev.id,
            Booking.status == "confirmed"
        ).scalar()
        sales_data.append(sold)

        admitted = db.query(Ticket).join(Booking).filter(
            Booking.event_id == ev.id,
            Ticket.status == "admitted"
        ).count()
        checkins_data.append(admitted)

    return {
        "labels": event_labels,
        "sales": sales_data,
        "checkins": checkins_data
    }
