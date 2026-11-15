import sys
import os
from datetime import datetime, timedelta

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine, Base, SessionLocal
from app.models import User, Venue, Event, TicketCategory, Booking, Ticket, AgentBelief, VenueHire
from app.security import hash_password
from app.agents import agent_bus
from app.agents.base import Performative
from app.schemas import AgentMessage

def seed_database():
    print("Initializing database tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Seed Users (Admin, Staff, Attendee)
        print("Seeding demo accounts...")
        users = [
            {
                "email": "admin@eventsphere.edu",
                "full_name": "Dr. Sarah Jenkins (Organiser)",
                "password": os.getenv("ADMIN_PASSWORD", "Admin@12345"),                "role": "admin"
            },
            {
                "email": "staff@eventsphere.edu",
                "full_name": "Marcus Vance (Gate Staff)",
                "password": os.getenv("STAFF_PASSWORD", "Staff@12345"),                "role": "staff"
            },
            {
                "email": "attendee@eventsphere.edu",
                "full_name": "Liam Chen (Student Attendee)",
                "password": "Attendee@12345",
                "role": "attendee"
            },
            {
                "email": "student@eventsphere.edu",
                "full_name": "Elena Rostova (Graduate Student)",
                "password": "Student@12345",
                "role": "attendee"
            }
        ]

        user_objects = {}
        for u in users:
            existing = db.query(User).filter(User.email == u["email"]).first()
            if not existing:
                user_obj = User(
                    email=u["email"],
                    full_name=u["full_name"],
                    hashed_password=hash_password(u["password"]),
                    role=u["role"]
                )
                db.add(user_obj)
                db.commit()
                db.refresh(user_obj)
                user_objects[u["email"]] = user_obj
                print(f"  Created user: {u['email']} [{u['role']}]")
            else:
                user_objects[u["email"]] = existing

        # 2. Seed Campus Venues
        print("Seeding campus venues...")
        venues_data = [
            {
                "name": "University Great Hall",
                "location": "Central Campus, Building A",
                "capacity": 500,
                "hourly_hire_rate": 150.0,
                "is_open_for_hire": True,
                "image_url": "https://images.unsplash.com/photo-1517457373958-b7bdd4587205?w=800&auto=format&fit=crop&q=80",
                "description": "Grand historic auditorium equipped with full theatrical acoustics, concert lighting, and tiered seating."
            },
            {
                "name": "Sirius Science Auditorium",
                "location": "North Wing, Level 2",
                "capacity": 250,
                "hourly_hire_rate": 80.0,
                "is_open_for_hire": True,
                "image_url": "https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=800&auto=format&fit=crop&q=80",
                "description": "Modern lecture and conference hall featuring dual high-definition projectors, surround sound, and breakout areas."
            },
            {
                "name": "Media & Creative Lab",
                "location": "Arts Complex, Studio 4",
                "capacity": 75,
                "hourly_hire_rate": 45.0,
                "is_open_for_hire": True,
                "image_url": "https://images.unsplash.com/photo-1492684223066-81342ee5ff30?w=800&auto=format&fit=crop&q=80",
                "description": "Flexible multi-purpose creative studio ideal for workshops, rehearsals, film screenings, and club receptions."
            },
            {
                "name": "Senate Executive Boardroom",
                "location": "Administration Tower, 5th Floor",
                "capacity": 30,
                "hourly_hire_rate": 60.0,
                "is_open_for_hire": False,
                "image_url": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&auto=format&fit=crop&q=80",
                "description": "Private boardroom reserved strictly for university governing councils and academic faculties."
            }
        ]

        venue_objects = {}
        for vd in venues_data:
            existing = db.query(Venue).filter(Venue.name == vd["name"]).first()
            if not existing:
                v = Venue(**vd)
                db.add(v)
                db.commit()
                db.refresh(v)
                venue_objects[vd["name"]] = v
                print(f"  Created venue: {v.name} (Cap: {v.capacity})")
            else:
                venue_objects[vd["name"]] = existing

        # 3. Seed Events with Ticket Categories
        print("Seeding upcoming events...")
        now = datetime.utcnow()
        events_data = [
            {
                "title": "Campus Symphony Orchestra Gala 2026",
                "category": "Concert",
                "venue_id": venue_objects["University Great Hall"].id,
                "start_time": now - timedelta(minutes=30),
                "end_time": now + timedelta(hours=3),
                "description": "An enchanting evening featuring Beethoven's 9th Symphony and modern cinematic scores performed live by the university philharmonic.",
                "image_url": "https://images.unsplash.com/photo-1465847899084-d164df4dedc6?w=800&auto=format&fit=crop&q=80",
                "status": "published",
                "categories": [
                    {"name": "VIP Premium", "price": 45.0, "total_quantity": 50, "available_quantity": 48},
                    {"name": "Standard Admission", "price": 25.0, "total_quantity": 300, "available_quantity": 298},
                    {"name": "Student Concession", "price": 15.0, "total_quantity": 150, "available_quantity": 150}
                ]
            },
            {
                "title": "AI & Multi-Agent Robotics Workshop",
                "category": "Workshop",
                "venue_id": venue_objects["Sirius Science Auditorium"].id,
                "start_time": now + timedelta(days=2, hours=2),
                "end_time": now + timedelta(days=2, hours=6),
                "description": "Hands-on masterclass in building cooperating software agents, FIPA-ACL messaging, and decentralized task coordination.",
                "image_url": "https://images.unsplash.com/photo-1531482615713-2afd69097998?w=800&auto=format&fit=crop&q=80",
                "status": "published",
                "categories": [
                    {"name": "General Participant", "price": 20.0, "total_quantity": 150, "available_quantity": 145},
                    {"name": "Student Pass", "price": 10.0, "total_quantity": 100, "available_quantity": 97}
                ]
            },
            {
                "title": "Annual University Tech & Career Fair",
                "category": "Conference",
                "venue_id": venue_objects["University Great Hall"].id,
                "start_time": now + timedelta(days=12, hours=1),
                "end_time": now + timedelta(days=12, hours=8),
                "description": "Connect with top technology employers, research laboratories, and startup founders offering internships and graduate roles.",
                "image_url": "https://images.unsplash.com/photo-1511578314322-379afb476865?w=800&auto=format&fit=crop&q=80",
                "status": "published",
                "categories": [
                    {"name": "All-Access Pass", "price": 10.0, "total_quantity": 450, "available_quantity": 448}
                ]
            }
        ]

        created_events = []
        for ed in events_data:
            existing = db.query(Event).filter(Event.title == ed["title"]).first()
            if not existing:
                cats = ed.pop("categories")
                ev = Event(**ed)
                db.add(ev)
                db.commit()
                db.refresh(ev)
                for c in cats:
                    tc = TicketCategory(event_id=ev.id, **c)
                    db.add(tc)
                db.commit()
                created_events.append(ev)
                print(f"  Created event: {ev.title}")
            else:
                created_events.append(existing)

        # 4. Seed Demo Bookings & QR Tickets for Instant Staff Scanning
        print("Seeding sample bookings and tickets for attendee...")
        attendee = user_objects["attendee@eventsphere.edu"]
        event1 = created_events[0]
        cat1 = db.query(TicketCategory).filter(TicketCategory.event_id == event1.id).first()

        existing_b = db.query(Booking).filter(Booking.user_id == attendee.id).first()
        if not existing_b:
            booking = Booking(
                user_id=attendee.id,
                event_id=event1.id,
                ticket_category_id=cat1.id,
                quantity=2,
                total_amount=cat1.price * 2,
                payment_reference="PAY-SIM-DEMO001",
                status="confirmed"
            )
            db.add(booking)
            db.commit()
            db.refresh(booking)

            # Ticket 1 (Valid)
            t1 = Ticket(
                booking_id=booking.id,
                ticket_code="TK-DEMO-VALID-01",
                status="valid",
                scan_count=0
            )
            # Ticket 2 (Already Admitted for Double Check-in Test)
            t2 = Ticket(
                booking_id=booking.id,
                ticket_code="TK-DEMO-USED-02",
                status="admitted",
                admitted_at=now - timedelta(minutes=15),
                scan_count=1
            )
            db.add_all([t1, t2])
            db.commit()
            print("  Created demo tickets: 'TK-DEMO-VALID-01' (Valid) and 'TK-DEMO-USED-02' (Admitted)")

        # 5. Seed a Sample Escalated Private Venue Hire
        existing_hire = db.query(VenueHire).first()
        if not existing_hire:
            hire = VenueHire(
                user_id=user_objects["student@eventsphere.edu"].id,
                venue_id=venue_objects["University Great Hall"].id,
                start_time=now + timedelta(days=20, hours=18),
                end_time=now + timedelta(days=20, hours=23),
                purpose="Graduation Alumni Reception & Dinner Party",
                guest_count=450,
                total_price=937.50,
                status="escalated",
                escalation_reason="Guest count (450) exceeds 80% capacity (500); High-impact activity purpose: 'Graduation Alumni Reception & Dinner Party'"
            )
            db.add(hire)
            db.commit()
            print("  Created sample escalated private venue hire request #1")

        # 6. Initialize Agent Beliefs
        beliefs = [
            ("VenueAgent", "turnaround_buffer_minutes", 60),
            ("TicketAgent", "total_tickets_issued", 2),
            ("TicketAgent", "total_tickets_admitted", 1),
            ("BookingAgent", "max_tickets_per_order", 6)
        ]
        for agent_name, key, val in beliefs:
            existing_blf = db.query(AgentBelief).filter(
                AgentBelief.agent_name == agent_name,
                AgentBelief.belief_key == key
            ).first()
            if not existing_blf:
                agent_bus.get_agent(agent_name).set_belief(db, key, val)

        print("\nSeed data completed successfully!")
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
