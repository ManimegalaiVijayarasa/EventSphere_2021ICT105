from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict, Field

# ----------------- User Schemas -----------------
class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role: Optional[str] = "attendee"

class UserLogin(BaseModel):
    email: str
    password: str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    full_name: str

# ----------------- Ticket Category Schemas -----------------
class TicketCategoryCreate(BaseModel):
    name: str
    price: float = Field(..., ge=0.0)
    total_quantity: int = Field(..., gt=0)

class TicketCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    name: str
    price: float
    total_quantity: int
    available_quantity: int

# ----------------- Venue Schemas -----------------
class VenueCreate(BaseModel):
    name: str
    location: str
    capacity: int = Field(..., gt=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    hourly_hire_rate: float = Field(..., gt=0.0)
    is_open_for_hire: bool = True

class VenueUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    capacity: Optional[int] = Field(None, gt=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    hourly_hire_rate: Optional[float] = Field(None, gt=0.0)
    is_open_for_hire: Optional[bool] = None

class VenueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str
    capacity: int
    description: Optional[str]
    image_url: Optional[str]
    hourly_hire_rate: float
    is_open_for_hire: bool
    created_at: datetime

# ----------------- Event Schemas -----------------
class EventCreate(BaseModel):
    title: str
    category: str
    venue_id: int
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    image_url: Optional[str] = None
    status: Optional[str] = "draft"
    ticket_categories: List[TicketCategoryCreate]

class EventUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    venue_id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    status: Optional[str] = None

class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category: str
    venue_id: int
    start_time: datetime
    end_time: datetime
    description: Optional[str]
    status: str
    image_url: Optional[str]
    created_at: datetime
    venue: Optional[VenueOut] = None
    ticket_categories: List[TicketCategoryOut] = []

# ----------------- Booking & Ticket Schemas -----------------
class CartHoldRequest(BaseModel):
    event_id: int
    ticket_category_id: int
    quantity: int = Field(..., gt=0, le=6)

class BookingCreate(BaseModel):
    event_id: int
    ticket_category_id: int
    quantity: int = Field(..., gt=0, le=6)
    cart_hold_id: Optional[int] = None

class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticket_code: str
    status: str
    admitted_at: Optional[datetime]
    scan_count: int
    last_scanned_at: Optional[datetime]

class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    event_id: int
    ticket_category_id: int
    quantity: int
    total_amount: float
    payment_reference: str
    status: str
    refund_amount: float
    created_at: datetime
    event: Optional[EventOut] = None
    ticket_category: Optional[TicketCategoryOut] = None
    tickets: List[TicketOut] = []

class TicketScanRequest(BaseModel):
    ticket_code: str
    event_id: Optional[int] = None

class TicketScanResponse(BaseModel):
    admit: bool
    status: str  # ADMITTED, ALREADY_USED, WRONG_EVENT, CANCELLED, OUTSIDE_CHECKIN_TIME, FRAUD_ALERT, NOT_FOUND
    reason: str
    ticket_code: str
    event_title: Optional[str] = None
    attendee_name: Optional[str] = None
    ticket_category: Optional[str] = None
    scan_count: int = 1
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# ----------------- Venue Hire Schemas -----------------
class VenueHireRequest(BaseModel):
    venue_id: int
    start_time: datetime
    end_time: datetime
    purpose: str
    guest_count: int = Field(..., gt=0)

class VenueHireDecisionResponse(BaseModel):
    hire_id: Optional[int] = None
    status: str  # CONFIRMED, COUNTER_PROPOSED, ESCALATED, REFUSED
    total_price: Optional[float] = None
    reason: str
    alternatives: Optional[List[Dict[str, Any]]] = None

class VenueHireReviewRequest(BaseModel):
    hire_id: int
    decision: str  # approved or rejected
    admin_notes: Optional[str] = None

# ----------------- Waitlist Schemas -----------------
class WaitlistJoinRequest(BaseModel):
    event_id: int
    ticket_category_id: int
    requested_quantity: int = Field(default=1, gt=0, le=6)

class WaitlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    event_id: int
    ticket_category_id: int
    status: str
    offer_expires_at: Optional[datetime]
    created_at: datetime
    event_title: Optional[str] = None
    category_name: Optional[str] = None

# ----------------- FIPA-ACL Agent Message Schema -----------------
class AgentMessage(BaseModel):
    message_id: str
    conversation_id: str
    sender: str
    receiver: str
    performative: str  # REQUEST, AGREE, REFUSE, PROPOSE, INFORM, FAILURE
    content: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class AgentMessageLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    message_id: str
    conversation_id: str
    sender: str
    receiver: str
    performative: str
    content: str
    created_at: datetime

# ----------------- Notification Schemas -----------------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    message: str
    channel: str
    is_read: bool
    created_at: datetime
