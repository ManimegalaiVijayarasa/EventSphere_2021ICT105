# IT4123 Agent Based Computing Practical — ICA 02
# EventSphere: Multi-Agent Campus Venue Booking & Digital Ticketing Platform
**Submission Date:** 15 November 2026  
**Module Code:** IT4123 Agent Based Computing Practical  
**Live Public Deployment:** `https://eventsphere-platform.onrender.com`  
**GitHub Repository:** `https://github.com/your-username/EventSphere`  

---

## 1. Executive Summary & Scenario
Universities manage a dynamic, multi-stakeholder ecosystem of venues and activities. Spaces such as auditoriums, conference halls, and creative studios must host scheduled institutional events (concerts, academic conferences, workshops) while concurrently accommodating private venue hire requests from student clubs and faculty for farewells, receptions, or meetings.

**EventSphere** resolves the complexity of scheduling conflicts, ticket allocation, and entrance admission by deploying an autonomous **Multi-Agent System (MAS)**. Rather than relying on static database CRUD routines, every critical business decision—whether approving an event slot, calculating peak pricing, preventing ticket overselling, passing freed seats to waitlisted customers, or validating digital tickets at the door—is arbitrated by **cooperating software agents** communicating via standard FIPA-ACL messages.

The platform is built with **FastAPI**, **Pydantic**, **SQLAlchemy** (supporting SQLite and PostgreSQL), and a modern **mobile-first responsive user interface (Bootstrap 5)** verified at 375 px phone width.

---

## 2. Multi-Agent System Architecture & Design (Part B)

### 2.1 Agent Roles, Goals, and Persistent Beliefs

| Agent | Goal | State & Persistent Beliefs | Documented Decision Rules |
| :--- | :--- | :--- | :--- |
| **`VenueAgent`** | Keep every venue's calendar free of clashes and arbitrate private hire. | - Calendar occupancy records<br>- Turnaround buffer rules ($60\text{ min}$)<br>- Peak multipliers ($1.15\times, 1.25\times$)<br>- Pending escalation count | 1. **Turnaround Buffer Rule:** Reject any slot if an existing event/hire exists within $start - 60\text{m}$ to $end + 60\text{m}$.<br>2. **Capacity Rule:** Refuse events if total tickets $> venue.capacity$.<br>3. **Peak & Weekend Pricing:** Apply $1.25\times$ base rate on weekends and $1.15\times$ between 18:00 and 22:00.<br>4. **Counter-Proposal Rule:** If a slot clashes, return `PROPOSE` with alternative times on the same day and alternative venues with matching capacity.<br>5. **Escalation Rule:** Routine hires ($\le 80\%$ capacity, standard purpose) are auto-confirmed. Requests $> 80\%$ capacity or high-impact purposes are escalated to admin. |
| **`BookingAgent`** | Sell tickets fairly without overselling, manage cart holds, and calculate refunds. | - Active cart holds<br>- Quota tables<br>- Total refunds issued counter | 1. **Quantity Limit Rule:** Enforce $1 \le quantity \le 6$ tickets per order.<br>2. **Concurrency Safety Rule:** Check $(available - active\_cart\_holds) \ge quantity$ atomically before reserving.<br>3. **Cart Hold Duration Rule:** Hold seats for exactly 10 minutes.<br>4. **Stated Refund Policy Rule:** $> 48\text{h}$ before event: 100% refund; $24 - 48\text{h}$: 50% refund; $< 24\text{h}$: 0% refund.<br>5. **Event Cancellation Rule:** Issue 100% full refunds automatically to all bookings when an organiser cancels an event. |
| **`TicketAgent`** | Admit each ticket exactly once and prevent fraudulent entry. | - Total tickets issued<br>- Total admitted tickets<br>- Duplicate scan counters<br>- Fraud alert threshold ($30\text{s}$) | 1. **Unguessable Code Rule:** Issue high-entropy 128-bit cryptographic tokens (`TK-XXXX`).<br>2. **Check-in Window Rule:** Allow admission only from 2 hours before event start to event end.<br>3. **Single Admission Rule:** Admitted tickets cannot be reused (`ALREADY_USED`).<br>4. **Fraud Detection Rule:** Repeated scans within 30 seconds trigger `FRAUD_ALERT` (possible shared screenshot).<br>5. **Gate Validation Rule:** Refuse tickets scanned at a different event (`WRONG_EVENT`) or cancelled tickets (`CANCELLED`). |
| **`WaitlistAgent`** | Pass freed seats to waiting customers fairly. | - FIFO queue per event/category<br>- Active seat offers<br>- Scheduled sweep statistics | 1. **FIFO Allocation Rule:** Prioritize waitlist entries by registration timestamp.<br>2. **Timed Hold Rule:** Give offered attendees exactly 15 minutes to claim.<br>3. **Reactive Reallocation Rule:** React to `SEATS_FREED` broadcast from `BookingAgent` by allocating seats immediately.<br>4. **Proactive Expiry Sweep Rule:** Sweep expired offers on a background timer, revoke hold, and re-offer to the next waiting customer. |
| **`NotificationAgent`** | Inform attendees and organisers of events that affect them. | - Delivery channels (in-app, email)<br>- Delivery audit counters | 1. **Listener Rule:** Intercept all broadcast and direct `INFORM` messages and convert them to user-visible alerts.<br>2. **Multi-Channel Rule:** Dispatch in-app notifications and simulated email logs. |

---

### 2.2 FIPA-ACL Message Passing Protocol

Agents do not make direct function or method calls to other agents. Instead, all agent coordination operates through standard FIPA-ACL compliant JSON messages:

```json
{
  "message_id": "b3e2182d-e069-450b-80a5-f8bb80d8f074",
  "conversation_id": "hire-84a1e9df",
  "sender": "VenueAgent",
  "receiver": "SystemUI",
  "performative": "PROPOSE",
  "content": {
    "reason": "Requested slot at 'University Great Hall' is unavailable (Clashes with event 'Spring Symphony' including 60m turnaround buffer).",
    "alternatives": [
      {
        "type": "alternative_time",
        "venue_name": "University Great Hall",
        "start_time": "2026-11-20T21:00:00",
        "end_time": "2026-11-20T23:00:00",
        "total_price": 345.0,
        "description": "Later slot on same day: 21:00 - 23:00"
      },
      {
        "type": "alternative_venue",
        "venue_name": "Sirius Science Auditorium",
        "capacity": 250,
        "total_price": 184.0,
        "description": "Alternative venue 'Sirius Science Auditorium' (Cap: 250)"
      }
    ]
  },
  "timestamp": "2026-11-15T10:15:30.123456"
}
```

### 2.3 Reactive vs. Proactive Agent Behaviour
1. **Reactive Behaviour:**
   - When an attendee cancels a booking, `BookingAgent` restocks capacity and broadcasts an `INFORM` message with action `SEATS_FREED`.
   - `WaitlistAgent` reactively intercepts this message, extracts the freed seat quantity, searches its FIFO queue, and immediately reserves a timed seat hold for the top waiting customer, notifying them through `NotificationAgent`.
2. **Proactive Behaviour:**
   - `WaitlistAgent` does not rely solely on user clicks. An asynchronous background timer worker continuously runs every 15 seconds (`TimerScheduler` $\to$ `PROACTIVE_SWEEP`).
   - The agent proactively sweeps all entries where `offer_expires_at < now`, revokes the hold, marks it `expired`, and automatically re-offers the seat to the next waiting customer without any human action.

---

## 3. Concurrency Handling & Seat Allocation Approach

A core challenge in high-demand event ticketing is the **race condition** where multiple users attempt to book the final available seat at the exact same moment.

### Our Strategy:
1. **Two-Tiered Seat Allocation (Cart Holds + Atomic Deductions):**
   - Attendees place a temporary 10-minute hold (`CartHold`).
   - The effective available seats are calculated dynamically:
     $$\text{Effective Available} = \text{Category Available} - \sum \text{Active Non-Expired Cart Holds}$$
2. **Database Row-Level Locking:**
   - In PostgreSQL, queries executing during booking utilize `SELECT ... FOR UPDATE` via SQLAlchemy (`with_for_update()`), ensuring serialized access to the ticket category row.
   - In SQLite, the engine is configured with transactions in WAL mode, ensuring atomic check-and-decrement operations:
     ```python
     category = db.query(TicketCategory).filter(
         TicketCategory.id == category_id
     ).with_for_update().first()
     
     if effective_available < requested_quantity:
         return self.build_message(performative=Performative.REFUSE, ...)
     
     category.available_quantity -= quantity
     db.commit()
     ```
3. **Verification in Pytest (`test_prevent_overselling_concurrency`):**
   - Verified that when remaining seats equals 1, two simultaneous requests result in exactly one `AGREE` and one `REFUSE`. The database available quantity never drops below 0.

---

## 4. Compulsory Functional Requirements (Part A)

### 4.1 Accounts and Roles
- **Registration & Authentication:** Attendees register with email, name, and password. Passwords are encrypted using salted `bcrypt` (12 rounds) and never stored in plain text.
- **Role Enforcement:** Three roles (`admin`, `staff`, `attendee`). FastAPI dependencies `require_role('admin')` and `require_role('staff', 'admin')` strictly guard routes. Unauthorised requests receive HTTP 403 Forbidden.

### 4.2 Venue Management (Admin)
- Admin can create and modify venues with name, location, capacity, hourly hire rate, image, and description.
- Flag `is_open_for_hire` enables or disables private hire availability.

### 4.3 Event Management (Admin)
- Events include title, category, venue, start/end time, description, and multiple ticket categories (VIP, Standard, Student).
- **VenueAgent Slot Validation:** Before saving, `VenueAgent` checks for clashing events and ensures the 60-minute turnaround cleaning buffer is preserved.
- **Event Cancellation:** Organiser cancellation triggers automated 100% full refunds and invalidates tickets through `BookingAgent`.

### 4.4 Browsing and Booking (Attendee)
- Mobile-responsive event catalogue with keyword search and category filtering.
- Displays remaining tickets per category in real time.
- Simulated payment generating traceable references (`PAY-SIM-XXXXXX`).
- Cancellation refund policy enforced strictly according to hours remaining.

### 4.5 Digital Tickets & Gate Staff Scanner
- Unique, unguessable cryptographic tokens (`TK-XXXX`).
- Mobile scanner interface utilizing camera via `html5-qrcode` plus manual entry fallback.
- Rejection of duplicates (`ALREADY_USED`), cancelled tickets (`CANCELLED`), wrong events (`WRONG_EVENT`), and outside check-in window.

### 4.6 Private Venue Hire (Attendee)
- Attendee submits date, time, guest count, and purpose.
- Routine requests confirmed automatically.
- Clashing slots generate counter-proposals with alternative times on the same day and alternative venues.
- High-occupancy ($>80\%$) and high-impact requests are escalated to the organiser for manual approval/rejection.

### 4.7 Organiser Dashboard (Admin)
- Real-time metric cards (Tickets Sold, Revenue, Check-Ins, Venues).
- Interactive Chart.js visualisations for sales and attendance.
- Audit inspector viewing all inter-agent FIPA messages with conversation filtering.

---

## 5. Part C – Advanced Features Implemented

1. **Waitlist with Timed Seat Holds & Visible Countdown:** 15-minute countdown timer on the frontend with proactive background sweep timer.
2. **Weekend & Peak-Time Pricing for Venue Hire:** `VenueAgent` dynamically applies $1.25\times$ for weekends and $1.15\times$ for peak evening hours (18:00 - 22:00).
3. **Suspicious Duplicate Scan Detection:** `TicketAgent` detects repeated scans of the same ticket within 30 seconds and raises a `FRAUD_ALERT` for shared screenshot fraud.
4. **Agents Reachable Over HTTP:** Every agent exposes an HTTP inbox at `/api/agents/{agent_name}/inbox`, accepting FIPA JSON messages.
5. **In-App & Simulated Email Notifications:** `NotificationAgent` formats events into real-time in-app dropdown alerts and simulated email dispatch logs.
6. **Visual Charts on Organiser Dashboard:** Embedded Chart.js charts for ticket sales per event and attendance ratios.
7. **Time-Limited Cart Holds:** 10-minute temporary seat reservation with live client-side countdown timer.
8. **Multi-Criteria Advanced Search:** Filter events by keyword, category, date, and venue.

---

## 6. Pytest Test Results & Verification Evidence

The test suite contains **17 meaningful unit and integration tests** covering all 5 agents, concurrency safety, ticket fraud detection, and refund rules.

```text
============================= test session starts =============================
platform win32 -- Python 3.12.0, pytest-9.2.0
rootdir: C:\Users\manim\.gemini\antigravity\scratch\EventSphere
plugins: anyio-4.15.1
collected 17 items

tests\test_agents.py::test_venue_agent_turnaround_buffer_clash PASSED    [  5%]
tests\test_agents.py::test_venue_agent_capacity_limit PASSED             [ 11%]
tests\test_agents.py::test_booking_agent_quantity_limit PASSED           [ 17%]
tests\test_agents.py::test_ticket_agent_issue_and_admit PASSED           [ 23%]
tests\test_agents.py::test_notification_agent_listener PASSED            [ 29%]
tests\test_agents.py::test_message_bus_traceability PASSED               [ 35%]
tests\test_concurrency.py::test_prevent_overselling_concurrency PASSED   [ 41%]
tests\test_concurrency.py::test_cart_hold_reservation_concurrency PASSED [ 47%]
tests\test_ticket_scanner.py::test_ticket_scanner_double_checkin_rejection PASSED [ 52%]
tests\test_ticket_scanner.py::test_ticket_scanner_fraud_alert_rapid_scans PASSED [ 58%]
tests\test_ticket_scanner.py::test_ticket_scanner_wrong_event_rejection PASSED [ 64%]
tests\test_venue_hire.py::test_venue_hire_routine_confirmation PASSED    [ 70%]
tests\test_venue_hire.py::test_venue_hire_counter_proposal_on_clash PASSED [ 76%]
tests\test_venue_hire.py::test_venue_hire_escalation_high_occupancy PASSED [ 82%]
tests\test_waitlist.py::test_waitlist_reactive_seat_release PASSED       [ 88%]
tests\test_waitlist.py::test_waitlist_proactive_sweep_expiry PASSED      [ 94%]
tests\test_waitlist.py::test_booking_refund_policy_rules PASSED          [100%]

============================= 17 passed in 13.97s =============================
```

---

## 7. Demo Accounts & Live Viva Walkthrough Guide

### Demo Credentials

| Role | Email | Password |
| :--- | :--- | :--- |
| **Admin / Organiser** | `admin@eventsphere.edu` | `Admin@12345` |
| **Gate Staff** | `staff@eventsphere.edu` | `Staff@12345` |
| **Student Attendee** | `attendee@eventsphere.edu` | `Attendee@12345` |

### Step-by-Step Live Viva Demonstration:
1. **Browse & Book:** Sign in as `attendee@eventsphere.edu`. Open an event, select tickets, place a cart hold (observe 10-min countdown timer), and click "Book Now". View your ticket and unique QR code under **My Digital Tickets**.
2. **Gate Entrance Check-in:** Sign in as `staff@eventsphere.edu`. Navigate to **Gate Scanner** (`/scanner`). Test scanning ticket code `TK-DEMO-VALID-01` (Admitted). Scan the same code again immediately (Fraud Alert / Already Used).
3. **Turnaround Buffer Verification:** Sign in as `admin@eventsphere.edu`. Go to **Manage Events** (`/admin/events`). Attempt to create an event overlapping an existing event slot or within its 60-minute turnaround buffer. Observe `VenueAgent` returning a refusal with exact clash details.
4. **Private Hire & Counter-Proposal:** Submit a private hire request for an occupied time slot. Observe `VenueAgent` responding with `PROPOSE` providing usable alternative time slots on the same day and alternative venues.
5. **Waitlist & Proactive Sweep:** Join a sold-out waitlist. Cancel another attendee's booking. Observe reactive seat offer with visible countdown, followed by automatic expiry and re-offering during the scheduled agent sweep.
6. **Agent Audit Logs:** Open **Multi-Agent Logs** (`/admin/agent-logs`) to follow the conversation ID tracking the entire multi-agent coordination flow.
