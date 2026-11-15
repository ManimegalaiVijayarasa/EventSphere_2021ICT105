import uuid
from datetime import datetime, timedelta
import pytest
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage
from app.models import MessageLog, Notification

def test_venue_agent_turnaround_buffer_clash(db, setup_seed_data):
    """VenueAgent must refuse any event that violates the turnaround buffer."""
    data = setup_seed_data
    existing_ev = data["event"]
    venue = data["venue1"]

    # Slot ending 30 min before existing event starts (within 60m buffer)
    clashing_start = existing_ev.start_time - timedelta(hours=2)
    clashing_end = existing_ev.start_time - timedelta(minutes=30)

    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="test-conv-001",
        sender="AdminUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_EVENT_SLOT",
            "venue_id": venue.id,
            "start_time": clashing_start.isoformat(),
            "end_time": clashing_end.isoformat(),
            "total_tickets": 50
        }
    )
    reply = agent_bus.send(msg, db=db)
    assert reply.performative == Performative.REFUSE
    assert "turnaround buffer" in reply.content["reason"].lower()

def test_venue_agent_capacity_limit(db, setup_seed_data):
    """VenueAgent must refuse event where total tickets exceed venue capacity."""
    data = setup_seed_data
    venue = data["venue1"]  # Capacity = 200

    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="test-conv-002",
        sender="AdminUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_EVENT_SLOT",
            "venue_id": venue.id,
            "start_time": (datetime.utcnow() + timedelta(days=20)).isoformat(),
            "end_time": (datetime.utcnow() + timedelta(days=20, hours=2)).isoformat(),
            "total_tickets": 250  # Exceeds 200
        }
    )
    reply = agent_bus.send(msg, db=db)
    assert reply.performative == Performative.REFUSE
    assert "exceeds venue capacity" in reply.content["reason"].lower()

def test_booking_agent_quantity_limit(db, setup_seed_data):
    """BookingAgent enforces maximum 6 tickets per booking."""
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]

    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="test-conv-003",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "HOLD_CART",
            "user_id": user.id,
            "event_id": ev.id,
            "ticket_category_id": cat.id,
            "quantity": 7  # Exceeds max 6
        }
    )
    reply = agent_bus.send(msg, db=db)
    assert reply.performative == Performative.REFUSE
    assert "must be between 1 and 6" in reply.content["reason"].lower()

def test_ticket_agent_issue_and_admit(db, setup_seed_data):
    """TicketAgent issues cryptographic code and admits valid ticket at the door."""
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]
    staff = data["staff"]

    # Book 1 ticket through BookingAgent
    book_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="test-conv-004",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CONFIRM_BOOKING",
            "user_id": user.id,
            "event_id": ev.id,
            "ticket_category_id": cat.id,
            "quantity": 1
        }
    )
    book_reply = agent_bus.send(book_msg, db=db)
    assert book_reply.performative == Performative.AGREE
    ticket_codes = book_reply.content["ticket_codes"]
    assert len(ticket_codes) == 1
    code = ticket_codes[0]
    assert code.startswith("TK-")

    # Set event start time to now so it falls inside check-in window
    ev.start_time = datetime.utcnow() + timedelta(minutes=30)
    ev.end_time = datetime.utcnow() + timedelta(hours=2)
    db.commit()

    # Scan at entrance via TicketAgent
    scan_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="test-conv-005",
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={
            "action": "VALIDATE_SCAN",
            "ticket_code": code,
            "event_id": ev.id,
            "staff_user_id": staff.id
        }
    )
    scan_reply = agent_bus.send(scan_msg, db=db)
    assert scan_reply.performative == Performative.AGREE
    assert scan_reply.content["admit"] is True
    assert scan_reply.content["status"] == "ADMITTED"

def test_notification_agent_listener(db, setup_seed_data):
    """NotificationAgent listens to broadcast events and writes in-app and email logs."""
    data = setup_seed_data
    user = data["attendee"]

    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="test-conv-006",
        sender="BookingAgent",
        receiver="NotificationAgent",
        performative=Performative.INFORM,
        content={
            "event_type": "TICKET_BOOKED",
            "user_id": user.id,
            "booking_id": 999,
            "event_title": "Grand Philharmonic",
            "quantity": 2,
            "total_amount": 50.0,
            "payment_reference": "PAY-SIM-TESTNOTIF"
        }
    )
    reply = agent_bus.send(msg, db=db)
    assert reply.performative == Performative.AGREE

    # Check notification in database
    notif = db.query(Notification).filter(
        Notification.user_id == user.id,
        Notification.title.ilike("%Grand Philharmonic%")
    ).first()
    assert notif is not None
    assert "PAY-SIM-TESTNOTIF" in notif.message

def test_message_bus_traceability(db):
    """Every message sent across agents is audited in MessageLog with conversation_id."""
    conv_id = f"trace-conv-{uuid.uuid4().hex[:6]}"
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        sender="TestAgent",
        receiver="NotificationAgent",
        performative=Performative.REQUEST,
        content={"action": "SEND_DIRECT_ALERT", "user_id": 1, "title": "Test", "text": "Trace test"}
    )
    agent_bus.send(msg, db=db)

    logs = db.query(MessageLog).filter(MessageLog.conversation_id == conv_id).all()
    # At least request + response logged
    assert len(logs) >= 2
    assert logs[0].conversation_id == conv_id
