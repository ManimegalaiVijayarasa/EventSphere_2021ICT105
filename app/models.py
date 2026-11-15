from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="attendee", nullable=False)  # admin, staff, attendee
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")
    venue_hires = relationship("VenueHire", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    waitlist_entries = relationship("WaitlistEntry", back_populates="user")


class Venue(Base):
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=False)
    capacity = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    hourly_hire_rate = Column(Float, nullable=False, default=100.0)
    is_open_for_hire = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("Event", back_populates="venue")
    venue_hires = relationship("VenueHire", back_populates="venue")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)  # Concert, Workshop, Seminar, Conference, etc.
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="draft", nullable=False)  # draft, published, cancelled
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    venue = relationship("Venue", back_populates="events")
    ticket_categories = relationship("TicketCategory", back_populates="event", cascade="all, delete-orphan")
    bookings = relationship("Booking", back_populates="event")
    waitlist_entries = relationship("WaitlistEntry", back_populates="event")


class TicketCategory(Base):
    __tablename__ = "ticket_categories"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    name = Column(String(100), nullable=False)  # VIP, Standard, Early Bird, Student
    price = Column(Float, nullable=False)
    total_quantity = Column(Integer, nullable=False)
    available_quantity = Column(Integer, nullable=False)

    event = relationship("Event", back_populates="ticket_categories")
    bookings = relationship("Booking", back_populates="ticket_category")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    total_amount = Column(Float, nullable=False)
    payment_reference = Column(String(100), nullable=False)
    status = Column(String(50), default="confirmed", nullable=False)  # confirmed, cancelled, refunded
    refund_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    event = relationship("Event", back_populates="bookings")
    ticket_category = relationship("TicketCategory", back_populates="bookings")
    tickets = relationship("Ticket", back_populates="booking", cascade="all, delete-orphan")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    ticket_code = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(50), default="valid", nullable=False)  # valid, admitted, cancelled
    admitted_at = Column(DateTime, nullable=True)
    check_in_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    scan_count = Column(Integer, default=0, nullable=False)
    last_scanned_at = Column(DateTime, nullable=True)

    booking = relationship("Booking", back_populates="tickets")


class CartHold(Base):
    __tablename__ = "cart_holds"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(50), default="active", nullable=False)  # active, converted, expired
    created_at = Column(DateTime, default=datetime.utcnow)


class WaitlistEntry(Base):
    __tablename__ = "waitlist_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    ticket_category_id = Column(Integer, ForeignKey("ticket_categories.id"), nullable=False)
    requested_quantity = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default="waiting", nullable=False)  # waiting, offered, claimed, expired
    offer_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="waitlist_entries")
    event = relationship("Event", back_populates="waitlist_entries")


class VenueHire(Base):
    __tablename__ = "venue_hires"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    venue_id = Column(Integer, ForeignKey("venues.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    purpose = Column(String(255), nullable=False)
    guest_count = Column(Integer, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String(50), default="confirmed", nullable=False)  # confirmed, counter_proposed, escalated, approved, rejected
    escalation_reason = Column(Text, nullable=True)
    counter_proposal_details = Column(Text, nullable=True)  # JSON representation of suggested slots/venues
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="venue_hires")
    venue = relationship("Venue", back_populates="venue_hires")


class MessageLog(Base):
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String(64), index=True, nullable=False)
    conversation_id = Column(String(64), index=True, nullable=False)
    sender = Column(String(100), nullable=False)
    receiver = Column(String(100), nullable=False)
    performative = Column(String(50), nullable=False)  # REQUEST, AGREE, REFUSE, PROPOSE, INFORM, FAILURE
    content = Column(Text, nullable=False)             # JSON payload
    created_at = Column(DateTime, default=datetime.utcnow)


class AgentBelief(Base):
    __tablename__ = "agent_beliefs"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String(100), index=True, nullable=False)
    belief_key = Column(String(100), index=True, nullable=False)
    belief_value = Column(Text, nullable=False)        # JSON string of persistent belief
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    channel = Column(String(50), default="in_app", nullable=False)  # in_app, email
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="notifications")
