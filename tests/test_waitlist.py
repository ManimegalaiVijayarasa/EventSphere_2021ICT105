import uuid
from datetime import datetime, timedelta
import pytest
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage
from app.models import WaitlistEntry, Booking, TicketCategory

def test_waitlist_reactive_seat_release(db, setup_seed_data):
    """
    When an attendee cancels a booking, BookingAgent reactively informs
    WaitlistAgent, which assigns a timed hold to the next waiting customer.
    """
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user1 = data["attendee"]
    user2 = data["attendee2"]

    # Book all 10 seats
    book_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="wl-test-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user1.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    b_reply = agent_bus.send(book_msg, db=db)
    booking_id = b_reply.content["booking_id"]

    # User 2 joins waitlist
    wl_join = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="wl-test-002",
        sender="SystemUI",
        receiver="WaitlistAgent",
        performative=Performative.REQUEST,
        content={"action": "JOIN_WAITLIST", "user_id": user2.id, "event_id": ev.id, "ticket_category_id": cat.id, "requested_quantity": 1}
    )
    wl_reply = agent_bus.send(wl_join, db=db)
    assert wl_reply.performative == Performative.AGREE
    wl_entry_id = wl_reply.content["waitlist_id"]

    # User 1 cancels booking
    cancel_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="wl-test-003",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CANCEL_BOOKING", "user_id": user1.id, "booking_id": booking_id}
    )
    cancel_reply = agent_bus.send(cancel_msg, db=db)
    assert cancel_reply.performative == Performative.AGREE

    # Verify User 2's waitlist status changed reactively from 'waiting' to 'offered'
    entry = db.query(WaitlistEntry).filter(WaitlistEntry.id == wl_entry_id).first()
    assert entry.status == "offered"
    assert entry.offer_expires_at is not None

def test_waitlist_proactive_sweep_expiry(db, setup_seed_data):
    """
    Proactive timer sweep expires unclaimed seats and automatically
    re-offers them or returns them to public capacity.
    """
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]

    # Create an expired waitlist offer in DB
    now = datetime.utcnow()
    past_entry = WaitlistEntry(
        user_id=user.id,
        event_id=ev.id,
        ticket_category_id=cat.id,
        requested_quantity=1,
        status="offered",
        offer_expires_at=now - timedelta(minutes=5)  # Expired 5 min ago
    )
    db.add(past_entry)
    db.commit()
    db.refresh(past_entry)

    # Trigger proactive sweep (as background worker does on timer)
    sweep_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="sweep-001",
        sender="TimerScheduler",
        receiver="WaitlistAgent",
        performative=Performative.REQUEST,
        content={"action": "PROACTIVE_SWEEP"}
    )
    sweep_reply = agent_bus.send(sweep_msg, db=db)
    assert sweep_reply.performative == Performative.INFORM
    assert sweep_reply.content["expired_count"] >= 1

    db.refresh(past_entry)
    assert past_entry.status == "expired"

def test_booking_refund_policy_rules(db, setup_seed_data):
    """Tests refund calculation for >48h (100%), 24-48h (50%), and <24h (0%)."""
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user = data["attendee"]

    # Scenario A: Event is 5 days away (>48h) -> 100% refund
    ev.start_time = datetime.utcnow() + timedelta(days=5)
    db.commit()

    book1 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="ref-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    b1_id = agent_bus.send(book1, db=db).content["booking_id"]

    cancel1 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="ref-002",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CANCEL_BOOKING", "user_id": user.id, "booking_id": b1_id}
    )
    rep1 = agent_bus.send(cancel1, db=db)
    assert rep1.content["refund_rate"] == 1.0

    # Scenario B: Event is 30 hours away (between 24h and 48h) -> 50% refund
    ev.start_time = datetime.utcnow() + timedelta(hours=30)
    db.commit()

    book2 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="ref-003",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    b2_id = agent_bus.send(book2, db=db).content["booking_id"]

    cancel2 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="ref-004",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CANCEL_BOOKING", "user_id": user.id, "booking_id": b2_id}
    )
    rep2 = agent_bus.send(cancel2, db=db)
    assert rep2.content["refund_rate"] == 0.50

    # Scenario C: Event is 5 hours away (<24h) -> 0% refund
    ev.start_time = datetime.utcnow() + timedelta(hours=5)
    db.commit()

    book3 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="ref-005",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CONFIRM_BOOKING", "user_id": user.id, "event_id": ev.id, "ticket_category_id": cat.id, "quantity": 1}
    )
    b3_id = agent_bus.send(book3, db=db).content["booking_id"]

    cancel3 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="ref-006",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={"action": "CANCEL_BOOKING", "user_id": user.id, "booking_id": b3_id}
    )
    rep3 = agent_bus.send(cancel3, db=db)
    assert rep3.content["refund_rate"] == 0.0
