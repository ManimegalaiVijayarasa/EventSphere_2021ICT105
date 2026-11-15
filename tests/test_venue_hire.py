import uuid
from datetime import datetime, timedelta
import pytest
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage

def test_venue_hire_routine_confirmation(db, setup_seed_data):
    """Routine private hire within normal parameters is confirmed automatically by VenueAgent."""
    data = setup_seed_data
    venue = data["venue2"]  # Capacity = 50, Rate = $40/hr
    user = data["attendee"]

    start = datetime.utcnow() + timedelta(days=10, hours=10)
    end = start + timedelta(hours=2)

    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="hire-test-001",
        sender="SystemUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "REQUEST_VENUE_HIRE",
            "user_id": user.id,
            "venue_id": venue.id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "purpose": "Study Group Review Session",
            "guest_count": 25  # <= 80% capacity (40)
        }
    )
    reply = agent_bus.send(msg, db=db)
    assert reply.performative == Performative.AGREE
    assert reply.content["status"] == "CONFIRMED"
    assert reply.content["total_price"] > 0

def test_venue_hire_counter_proposal_on_clash(db, setup_seed_data):
    """When a slot clashes, VenueAgent counter-proposes usable alternative times or venues."""
    data = setup_seed_data
    ev = data["event"]
    venue = data["venue1"]
    user = data["attendee"]

    # Request hire directly during existing event
    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="hire-clash-001",
        sender="SystemUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "REQUEST_VENUE_HIRE",
            "user_id": user.id,
            "venue_id": venue.id,
            "start_time": ev.start_time.isoformat(),
            "end_time": ev.end_time.isoformat(),
            "purpose": "Club Reception",
            "guest_count": 40
        }
    )
    reply = agent_bus.send(msg, db=db)
    # Must be PROPOSE (not just flat refusal)
    assert reply.performative == Performative.PROPOSE
    assert "alternatives" in reply.content
    assert len(reply.content["alternatives"]) > 0

def test_venue_hire_escalation_high_occupancy(db, setup_seed_data):
    """When guest count exceeds 80% capacity, VenueAgent escalates request to organiser."""
    data = setup_seed_data
    venue = data["venue2"]  # Capacity = 50
    user = data["attendee"]

    start = datetime.utcnow() + timedelta(days=15, hours=12)
    end = start + timedelta(hours=3)

    msg = AgentMessage(
        message_id=str(uuid.uuid4()),
        conversation_id="hire-esc-001",
        sender="SystemUI",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "REQUEST_VENUE_HIRE",
            "user_id": user.id,
            "venue_id": venue.id,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "purpose": "Large Department Party",
            "guest_count": 45  # 90% of capacity (50)
        }
    )
    reply = agent_bus.send(msg, db=db)
    assert reply.performative == Performative.PROPOSE
    assert reply.content["status"] == "ESCALATED"
    assert "escalated" in reply.content["reason"].lower()
