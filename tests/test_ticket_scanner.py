import uuid
from datetime import datetime, timedelta
import pytest
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage
from app.models import Ticket, Booking

def test_ticket_scanner_double_checkin_rejection(db, setup_seed_data):
    """A ticket is admitted once only; second scan is rejected with 'ALREADY_USED'."""
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]
    staff = data["staff"]

    ev.start_time = datetime.utcnow() + timedelta(minutes=20)
    ev.end_time = datetime.utcnow() + timedelta(hours=2)
    db.commit()

    # Book ticket
    book_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="scan-test-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    code = agent_bus.send(book_msg, db=db).content["ticket_codes"][0]

    # First Scan -> ADMITTED
    scan1 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="scan-test-002",
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={"action": "VALIDATE_SCAN", "ticket_code": code, "event_id": ev.id, "staff_user_id": staff.id}
    )
    reply1 = agent_bus.send(scan1, db=db)
    assert reply1.content["admit"] is True
    assert reply1.content["status"] == "ADMITTED"

    # Fast forward last scan time to beyond suspicious window (e.g. 5 minutes ago)
    t = db.query(Ticket).filter(Ticket.ticket_code == code).first()
    t.last_scanned_at = datetime.utcnow() - timedelta(minutes=5)
    db.commit()

    # Second Scan -> REJECTED (ALREADY_USED)
    scan2 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="scan-test-003",
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={"action": "VALIDATE_SCAN", "ticket_code": code, "event_id": ev.id, "staff_user_id": staff.id}
    )
    reply2 = agent_bus.send(scan2, db=db)
    assert reply2.content["admit"] is False
    assert reply2.content["status"] == "ALREADY_USED"
    assert "already admitted" in reply2.content["reason"].lower()

def test_ticket_scanner_fraud_alert_rapid_scans(db, setup_seed_data):
    """Detection of suspicious repeated scans within 30s triggers FRAUD_ALERT."""
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]
    staff = data["staff"]

    ev.start_time = datetime.utcnow() + timedelta(minutes=20)
    ev.end_time = datetime.utcnow() + timedelta(hours=2)
    db.commit()

    # Book ticket
    book_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="fraud-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    code = agent_bus.send(book_msg, db=db).content["ticket_codes"][0]

    # First Scan
    agent_bus.send(AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="fraud-002",
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={"action": "VALIDATE_SCAN", "ticket_code": code, "event_id": ev.id, "staff_user_id": staff.id}
    ), db=db)

    # Immediate second scan (simulating two people entering at different gates using shared screenshot)
    rapid_scan = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="fraud-003",
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={"action": "VALIDATE_SCAN", "ticket_code": code, "event_id": ev.id, "staff_user_id": staff.id}
    )
    rapid_reply = agent_bus.send(rapid_scan, db=db)
    assert rapid_reply.content["admit"] is False
    assert rapid_reply.content["status"] == "FRAUD_ALERT"
    assert "suspicious" in rapid_reply.content["reason"].lower()

def test_ticket_scanner_wrong_event_rejection(db, setup_seed_data):
    """Ticket scanned at wrong event gate is rejected with 'WRONG_EVENT'."""
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]
    staff = data["staff"]

    ev.start_time = datetime.utcnow() + timedelta(minutes=20)
    ev.end_time = datetime.utcnow() + timedelta(hours=2)
    db.commit()

    # Book ticket for ev
    book_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="wrong-ev-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    code = agent_bus.send(book_msg, db=db).content["ticket_codes"][0]

    # Scan with different event_id (9999)
    scan_wrong = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="wrong-ev-002",
        sender="GateStaffUI",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={"action": "VALIDATE_SCAN", "ticket_code": code, "event_id": 9999, "staff_user_id": staff.id}
    )
    reply = agent_bus.send(scan_wrong, db=db)
    assert reply.content["admit"] is False
    assert reply.content["status"] == "WRONG_EVENT"
