import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.agents import agent_bus
from app.agents.base import Performative
from app.database import get_db
from app.models import Event, User
from app.schemas import TicketScanRequest, TicketScanResponse, AgentMessage
from app.security import get_staff_or_admin_user

router = APIRouter(tags=["Gate Staff Scanner"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/scanner", response_class=HTMLResponse)
def scanner_page(
    request: Request,
    user: User = Depends(get_staff_or_admin_user),
    db: Session = Depends(get_db)
):
    active_events = db.query(Event).filter(Event.status == "published").all()
    return templates.TemplateResponse(
        request=request,
        name="staff_scanner.html",
        context={
            "user": user,
            "events": active_events
        }
    )

@router.post("/api/staff/scan", response_model=TicketScanResponse)
def scan_ticket_api(
    payload: TicketScanRequest,
    user: User = Depends(get_staff_or_admin_user),
    db: Session = Depends(get_db)
):
    conv_id = f"scan-{uuid.uuid4().hex[:8]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={
            "action": "VALIDATE_SCAN",
            "ticket_code": payload.ticket_code.strip(),
            "event_id": payload.event_id,
            "staff_user_id": user.id
        }
    )
    reply = agent_bus.send(msg, db=db)
    content = reply.content

    return TicketScanResponse(
        admit=content.get("admit", False),
        status=content.get("status", "UNKNOWN"),
        reason=content.get("reason", "Scan processed."),
        ticket_code=payload.ticket_code,
        event_title=content.get("event_title"),
        attendee_name=content.get("attendee_name"),
        ticket_category=content.get("ticket_category"),
        scan_count=content.get("scan_count", 1)
    )
