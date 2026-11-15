import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.agents import agent_bus
from app.agents.base import Performative
from app.database import get_db
from app.models import Booking, Ticket, WaitlistEntry, Event, TicketCategory, User
from app.schemas import (
    CartHoldRequest,
    BookingCreate,
    WaitlistJoinRequest,
    AgentMessage
)
from app.security import get_current_user, get_current_user_optional
from app.utils import generate_qr_data_uri

router = APIRouter(tags=["Bookings & Tickets"])
templates = Jinja2Templates(directory="app/templates")

# --- HTML Web Views ---
@router.get("/my-bookings", response_class=HTMLResponse)
def my_bookings_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    bookings = db.query(Booking).filter(
        Booking.user_id == user.id
    ).order_by(Booking.created_at.desc()).all()

    # Pre-generate QR codes for valid tickets
    ticket_data = []
    for b in bookings:
        for t in b.tickets:
            qr_uri = generate_qr_data_uri(t.ticket_code) if t.status == "valid" else None
            ticket_data.append({
                "ticket": t,
                "booking": b,
                "event": b.event,
                "qr_uri": qr_uri
            })

    return templates.TemplateResponse("my_bookings.html", {
        "request": request,
        "user": user,
        "bookings": bookings,
        "tickets": ticket_data,
        "now": datetime.utcnow()
    })

@router.get("/waitlist", response_class=HTMLResponse)
def waitlist_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    entries = db.query(WaitlistEntry).filter(
        WaitlistEntry.user_id == user.id
    ).order_by(WaitlistEntry.created_at.desc()).all()

    return templates.TemplateResponse("waitlist.html", {
        "request": request,
        "user": user,
        "entries": entries,
        "now": datetime.utcnow()
    })

# --- REST API Endpoints with FIPA-ACL Agent Message Passing ---

@router.post("/api/bookings/hold")
def hold_cart_api(
    payload: CartHoldRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv_id = f"cart-hold-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "HOLD_CART",
            "user_id": user.id,
            "event_id": payload.event_id,
            "ticket_category_id": payload.ticket_category_id,
            "quantity": payload.quantity
        }
    )
    reply = agent_bus.send(msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Could not place cart hold.")
        )
    return reply.content

@router.post("/api/bookings/confirm")
def confirm_booking_api(
    payload: BookingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv_id = f"book-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CONFIRM_BOOKING",
            "user_id": user.id,
            "event_id": payload.event_id,
            "ticket_category_id": payload.ticket_category_id,
            "quantity": payload.quantity,
            "cart_hold_id": payload.cart_hold_id
        }
    )
    reply = agent_bus.send(msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Booking failed.")
        )
    return reply.content

@router.post("/api/bookings/{booking_id}/cancel")
def cancel_booking_api(
    booking_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv_id = f"cancel-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CANCEL_BOOKING",
            "user_id": user.id,
            "booking_id": booking_id
        }
    )
    reply = agent_bus.send(msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Cancellation failed.")
        )
    return reply.content

@router.post("/api/waitlist/join")
def join_waitlist_api(
    payload: WaitlistJoinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv_id = f"waitlist-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="SystemUI",
        receiver="WaitlistAgent",
        performative=Performative.REQUEST,
        content={
            "action": "JOIN_WAITLIST",
            "user_id": user.id,
            "event_id": payload.event_id,
            "ticket_category_id": payload.ticket_category_id,
            "requested_quantity": payload.requested_quantity
        }
    )
    reply = agent_bus.send(msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Could not join waitlist.")
        )
    return reply.content

@router.post("/api/waitlist/{waitlist_id}/claim")
def claim_waitlist_api(
    waitlist_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv_id = f"wl-claim-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="SystemUI",
        receiver="WaitlistAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CLAIM_SEAT",
            "user_id": user.id,
            "waitlist_id": waitlist_id
        }
    )
    reply = agent_bus.send(msg, db=db)
    if reply.performative != Performative.AGREE:
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Could not claim seat.")
        )
    return reply.content
