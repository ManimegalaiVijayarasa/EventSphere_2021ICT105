import uuid
from datetime import datetime, timedelta
import pytest
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage
from app.models import TicketCategory, Booking

def test_prevent_overselling_concurrency(db, setup_seed_data):
    """
    Ensures that when available tickets drop to 1, two booking attempts
    cannot oversell the category. One succeeds, the second is refused.
    """
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user1 = data["attendee"]
    user2 = data["attendee2"]

    # Set remaining capacity strictly to 1 seat
    cat.available_quantity = 1
    db.commit()

    # User 1 requests the last seat
    msg1 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="race-conv-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CONFIRM_BOOKING",
            "user_id": user1.id,
            "event_id": ev.id,
            "ticket_category_id": cat.id,
            "quantity": 1
        }
    )
    reply1 = agent_bus.send(msg1, db=db)
    assert reply1.performative == Performative.AGREE
    assert reply1.content["status"] == "confirmed"

    # User 2 attempts to book the seat at the same time
    msg2 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="race-conv-002",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CONFIRM_BOOKING",
            "user_id": user2.id,
            "event_id": ev.id,
            "ticket_category_id": cat.id,
            "quantity": 1
        }
    )
    reply2 = agent_bus.send(msg2, db=db)
    assert reply2.performative == Performative.REFUSE
    assert "available" in reply2.content["reason"].lower()

    # Final verify: Available seats is 0, never negative!
    db.refresh(cat)
    assert cat.available_quantity == 0

def test_cart_hold_reservation_concurrency(db, setup_seed_data):
    """
    When User 1 holds the last seat in cart, User 2 cannot book it
    even if User 1 hasn't finished payment yet.
    """
    data = setup_seed_data
    ev = data["event"]
    cat = data["category"]
    user1 = data["attendee"]
    user2 = data["attendee2"]

    cat.available_quantity = 1
    db.commit()

    # User 1 holds cart
    hold_msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="hold-race-001",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "HOLD_CART",
            "user_id": user1.id,
            "event_id": ev.id,
            "ticket_category_id": cat.id,
            "quantity": 1
        }
    )
    hold_reply = agent_bus.send(hold_msg, db=db)
    assert hold_reply.performative == Performative.AGREE

    # User 2 attempts to hold or book the same seat
    hold_msg2 = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="hold-race-002",
        sender="SystemUI",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "HOLD_CART",
            "user_id": user2.id,
            "event_id": ev.id,
            "ticket_category_id": cat.id,
            "quantity": 1
        }
    )
    hold_reply2 = agent_bus.send(hold_msg2, db=db)
    assert hold_reply2.performative == Performative.REFUSE
    assert "insufficient seats" in hold_reply2.content["reason"].lower()
