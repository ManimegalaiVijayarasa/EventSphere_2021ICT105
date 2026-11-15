from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import get_db
from app.models import Event, Venue, TicketCategory, User
from app.schemas import EventOut
from app.security import get_current_user_optional

router = APIRouter(tags=["Events"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
def index_page(
    request: Request,
    q: Optional[str] = Query(None, description="Search keyword"),
    category: Optional[str] = Query(None, description="Event category"),
    venue_id: Optional[int] = Query(None, description="Venue ID"),
    date_from: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    query = db.query(Event).filter(Event.status == "published")

    if q:
        query = query.filter(
            or_(
                Event.title.ilike(f"%{q}%"),
                Event.description.ilike(f"%{q}%")
            )
        )
    if category and category.lower() != "all":
        query = query.filter(Event.category == category)
    if venue_id:
        query = query.filter(Event.venue_id == venue_id)
    if date_from:
        try:
            dt = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Event.start_time >= dt)
        except ValueError:
            pass

    events = query.order_by(Event.start_time.asc()).all()
    categories = db.query(Event.category).distinct().all()
    categories_list = [c[0] for c in categories if c[0]]
    venues = db.query(Venue).all()

    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "events": events,
        "categories": categories_list,
        "venues": venues,
        "selected_category": category,
        "search_query": q,
        "selected_venue": venue_id
    })

@router.get("/events/{event_id}", response_class=HTMLResponse)
def event_detail_page(
    request: Request,
    event_id: int,
    user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    return templates.TemplateResponse("event_detail.html", {
        "request": request,
        "user": user,
        "event": event
    })

# --- REST API Endpoints ---
@router.get("/api/events", response_model=List[EventOut])
def get_events_api(
    q: Optional[str] = None,
    category: Optional[str] = None,
    venue_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Event).filter(Event.status == "published")
    if q:
        query = query.filter(or_(Event.title.ilike(f"%{q}%"), Event.description.ilike(f"%{q}%")))
    if category and category.lower() != "all":
        query = query.filter(Event.category == category)
    if venue_id:
        query = query.filter(Event.venue_id == venue_id)

    return query.order_by(Event.start_time.asc()).all()

@router.get("/api/events/{event_id}", response_model=EventOut)
def get_event_detail_api(event_id: int, db: Session = Depends(get_db)):
    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
