import os
import sys
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import Base
from app.models import User, Venue, Event, TicketCategory, Booking, Ticket, WaitlistEntry
from app.security import hash_password
from app.agents import agent_bus

TEST_DB_URL = "sqlite:///./test_eventsphere.db"

@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test_eventsphere.db"):
        try:
            os.remove("./test_eventsphere.db")
        except Exception:
            pass

@pytest.fixture(scope="function")
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def setup_seed_data(db):
    # Create test users
    admin = User(
        email="testadmin@eventsphere.edu",
        full_name="Admin User",
        hashed_password=hash_password("Pass@123"),
        role="admin"
    )
    staff = User(
        email="teststaff@eventsphere.edu",
        full_name="Staff User",
        hashed_password=hash_password("Pass@123"),
        role="staff"
    )
    attendee = User(
        email="testattendee@eventsphere.edu",
        full_name="Attendee One",
        hashed_password=hash_password("Pass@123"),
        role="attendee"
    )
    attendee2 = User(
        email="testattendee2@eventsphere.edu",
        full_name="Attendee Two",
        hashed_password=hash_password("Pass@123"),
        role="attendee"
    )
    db.add_all([admin, staff, attendee, attendee2])
    db.commit()

    # Create test venues
    v1 = Venue(
        name="Main Concert Hall",
        location="Campus Zone A",
        capacity=200,
        hourly_hire_rate=100.0,
        is_open_for_hire=True
    )
    v2 = Venue(
        name="Seminar Room B",
        location="Campus Zone B",
        capacity=50,
        hourly_hire_rate=40.0,
        is_open_for_hire=True
    )
    v_closed = Venue(
        name="Private Lab",
        location="Zone C",
        capacity=20,
        hourly_hire_rate=50.0,
        is_open_for_hire=False
    )
    db.add_all([v1, v2, v_closed])
    db.commit()

    # Create test event
    now = datetime.utcnow()
    ev = Event(
        title="Spring Symphony 2026",
        category="Concert",
        venue_id=v1.id,
        start_time=now + timedelta(days=5),
        end_time=now + timedelta(days=5, hours=3),
        status="published"
    )
    db.add(ev)
    db.commit()

    cat1 = TicketCategory(
        event_id=ev.id,
        name="Standard",
        price=20.0,
        total_quantity=10,
        available_quantity=10
    )
    db.add(cat1)
    db.commit()

    return {
        "admin": admin,
        "staff": staff,
        "attendee": attendee,
        "attendee2": attendee2,
        "venue1": v1,
        "venue2": v2,
        "venue_closed": v_closed,
        "event": ev,
        "category": cat1
    }
