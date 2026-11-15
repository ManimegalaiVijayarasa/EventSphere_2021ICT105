import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.agents import agent_bus
from app.agents.base import Performative
from app.database import get_db
from app.models import Venue, VenueHire, User
from app.schemas import VenueHireRequest, VenueHireDecisionResponse, VenueOut, AgentMessage
from app.security import get_current_user, get_current_user_optional

router = APIRouter(tags=["Venues & Private Hire"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/venues", response_class=HTMLResponse)
def venues_page(
    request: Request,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    venues = db.query(Venue).all()
    user_hires = []
    if user:
        user_hires = db.query(VenueHire).filter(
            VenueHire.user_id == user.id
        ).order_by(VenueHire.created_at.desc()).all()

    return templates.TemplateResponse(
        request=request,
        name="venues.html",
        context={
            "user": user,
            "venues": venues,
            "user_hires": user_hires,
            "now": datetime.utcnow()
        }
    )

@router.get("/hire-status/{hire_id}", response_class=HTMLResponse)
def hire_status_page(
    request: Request,
    hire_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    hire = db.query(VenueHire).filter(
        VenueHire.id == hire_id,
        VenueHire.user_id == user.id
    ).first()
    if not hire:
        raise HTTPException(status_code=404, detail="Hire request not found.")

    return templates.TemplateResponse(
        request=request,
        name="hire_status.html",
        context={
            "user": user,
            "hire": hire
        }
    )

# --- REST API Endpoints ---
@router.get("/api/venues", response_model=List[VenueOut])
def get_venues_api(db: Session = Depends(get_db)):
    return db.query(Venue).all()

@router.post("/api/venues/hire", response_model=VenueHireDecisionResponse)
def request_venue_hire_api(
    payload: VenueHireRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="End time must be after start time.")

    conv_id = f"hire-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="SystemUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "REQUEST_VENUE_HIRE",
            "user_id": user.id,
            "venue_id": payload.venue_id,
            "start_time": payload.start_time.isoformat(),
            "end_time": payload.end_time.isoformat(),
            "purpose": payload.purpose,
            "guest_count": payload.guest_count
        }
    )
    reply = agent_bus.send(msg, db=db)

    if reply.performative == Performative.AGREE:
        return {
            "hire_id": reply.content.get("hire_id"),
            "status": reply.content.get("status", "CONFIRMED"),
            "total_price": reply.content.get("total_price"),
            "reason": reply.content.get("reason", "Routine request confirmed."),
            "alternatives": None
        }
    elif reply.performative == Performative.PROPOSE:
        return {
            "hire_id": reply.content.get("hire_id"),
            "status": reply.content.get("status", "COUNTER_PROPOSED"),
            "total_price": reply.content.get("total_price"),
            "reason": reply.content.get("reason", "Alternative proposed or escalated."),
            "alternatives": reply.content.get("alternatives")
        }
    else:
        # REFUSE or FAILURE
        raise HTTPException(
            status_code=400,
            detail=reply.content.get("reason", "Venue hire request was refused.")
        )
