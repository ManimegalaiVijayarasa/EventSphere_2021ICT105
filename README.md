# EventSphere - Multi-Agent Campus Venue Booking & Digital Ticketing Platform

**Module:** IT4123 Agent Based Computing Practical  
**Assignment:** ICA 02  
**Architecture:** FIPA-ACL Multi-Agent System with FastAPI, SQLite/PostgreSQL, Bootstrap 5 (Mobile-First 375px), and Pytest.

---

## 🚀 Live Public Deployment & Demo Accounts

* **Live Cloud URL:** `https://eventsphere-platform.onrender.com` (or your deployed Render URL)
* **API Documentation (Swagger):** `/docs` and `/redoc`

### Demo Accounts

| Role | Email | Password | Access & Responsibilities |
| :--- | :--- | :--- | :--- |
| **Admin / Organiser** | `admin@eventsphere.edu` | `Admin@12345` | Venue & event creation, ticket categories, draft/publish/cancel, review escalated hires, agent message logs, sales & check-in charts |
| **Gate Staff** | `staff@eventsphere.edu` | `Staff@12345` | Entrance check-in camera QR scanner, duplicate/wrong event/fraud detection, manual fallback |
| **Attendee (Student)** | `attendee@eventsphere.edu` | `Attendee@12345` | Browse events, cart hold countdown, simulated booking, digital QR ticket wallet, cancellation refund, waitlist |
| **Attendee (Grad Student)** | `student@eventsphere.edu` | `Student@12345` | Private venue hire requests, counter-proposal review |

> **Note:** The login page (`/login`) includes 1-click quick fill buttons for instant demo switching during live assessment.

---

## 🏛️ Multi-Agent Architecture (Part B Compliance)

In EventSphere, every booking, scheduling, ticket validation, and seat-release decision is made strictly by **autonomous cooperating software agents** exchanging structured JSON messages carrying **FIPA performatives** (`REQUEST`, `AGREE`, `REFUSE`, `PROPOSE`, `INFORM`, `FAILURE`). Database calls renamed as "agents" are strictly avoided.

```
                    ┌───────────────────────────┐
                    │      AgentMessageBus      │
                    └─────────────┬─────────────┘
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
   │ VenueAgent  │         │BookingAgent │         │ TicketAgent │
   └──────┬──────┘         └──────┬──────┘         └──────┬──────┘
          │                       │                       │
          │                       ▼                       │
          │                ┌─────────────┐                │
          │                │WaitlistAgent│                │
          │                └──────┬──────┘                │
          │                       │                       │
          ▼                       ▼                       ▼
   ┌─────────────────────────────────────────────────────────────┐
   │                      NotificationAgent                      │
   └─────────────────────────────────────────────────────────────┘
```

### Required Agents & Documented Decision Rules

1. **`VenueAgent`**
   - **Goal:** Keep every venue's calendar free of clashes and manage reservations.
   - **Decision Rules:**
     - *Turnaround Buffer:* Enforces a mandatory 60-minute turnaround cleaning/setup buffer between any two activities at a venue.
     - *Capacity Constraint:* Refuses any event where total ticket quantities exceed venue capacity.
     - *Dynamic Peak Pricing:* Multiplies hourly rate by `1.25x` on weekends and `1.15x` during peak evening hours (18:00 - 22:00).
     - *Intelligent Counter-Proposals:* When a requested hire slot clashes, `VenueAgent` does not simply refuse; it responds with `PROPOSE` containing concrete alternative time slots on the same day and alternative venues with matching capacity.
     - *Escalation Threshold:* Routine requests (guest count $\le$ 80% capacity and standard purpose) are auto-confirmed. Requests $> 80\%$ capacity or high-impact purposes (concerts, large receptions) are escalated to the organiser.
   - **Communicates with:** `NotificationAgent`.

2. **`BookingAgent`**
   - **Goal:** Sell tickets fairly without overselling, manage cart holds, and calculate refunds.
   - **Decision Rules:**
     - *Quantity Limit:* Max 6 tickets per order.
     - *Concurrency-Safe Capacity:* Atomically decrements remaining tickets and respects active 10-minute cart holds (`CartHold`).
     - *Cancellation Refund Policy:*
       - $> 48$ hours before event start: **100% refund**.
       - $24 - 48$ hours before event start: **50% refund**.
       - $< 24$ hours before event start: **0% refund**.
     - *Organiser Event Cancellation:* Automatically triggers **100% full refund** for all bookings and invalidates tickets.
   - **Communicates with:** `TicketAgent`, `WaitlistAgent`, `NotificationAgent`.

3. **`TicketAgent`**
   - **Goal:** Issue cryptographically unguessable codes and admit each ticket exactly once.
   - **Decision Rules:**
     - *Issuance:* Generates high-entropy tokens (`TK-{secrets.token_urlsafe(16)}`).
     - *Admission Logic:*
       - If valid & within check-in window (2 hours before event start to event end): returns `ADMITTED`.
       - If already scanned earlier: returns `ALREADY_USED`.
       - If repeated scans occur within 30 seconds: flags `FRAUD_ALERT` (shared screenshot detection).
       - If scanned at wrong event gate: returns `WRONG_EVENT`.
       - If cancelled/refunded: returns `CANCELLED`.
   - **Communicates with:** `BookingAgent`.

4. **`WaitlistAgent`**
   - **Goal:** Pass freed seats to waiting customers with timed holds.
   - **Decision Rules:**
     - *FIFO Queue:* Prioritizes waitlist entries by timestamp.
     - *Reactive Behaviour:* Listens to `SEATS_FREED` broadcast from `BookingAgent` when tickets are cancelled, immediately allocating 15-minute reservation holds to waiting attendees.
     - *Proactive Behaviour:* Acts on an automated continuous background timer loop without user intervention to expire unclaimed holds and re-offer seats to the next attendee or return them to public capacity.
   - **Communicates with:** `BookingAgent`, `NotificationAgent`.

5. **`NotificationAgent`**
   - **Goal:** Inform attendees and organizers of events that affect them.
   - **Decision Rules:**
     - Translates broadcast and direct `INFORM` messages into in-app notifications and simulated email dispatches (`TICKET_BOOKED`, `HIRE_CONFIRMED`, `WAITLIST_SEAT_OFFERED`, `REFUND_ISSUED`).
   - **Communicates with:** All agents.

---

## 🌟 Part C – Advanced Features Implemented

1. **Proactive Waitlist with Timed Seat Holds & Visible Countdown:** 15-minute countdown timer on the frontend with proactive background sweep timer.
2. **Dynamic Weekend & Peak-Time Venue Pricing:** Decided autonomously by `VenueAgent`.
3. **Suspicious Repeated Scan Fraud Detection:** `TicketAgent` detects duplicate scans within 30 seconds and triggers a security fraud alert.
4. **Agent HTTP Inboxes:** Every agent is reachable over HTTP at `/api/agents/{agent_name}/inbox`, accepting standard JSON ACL messages and documented in the OpenAPI Swagger UI.
5. **In-App & Simulated Email Notifications:** Real-time dropdown notification center with unread badges.
6. **Organiser Analytics & Charts:** Interactive Chart.js graphs displaying ticket sales per event and real-time attendance ratios.
7. **Time-Limited Cart Holds:** Temporary 10-minute seat lock with live countdown.
8. **Advanced Search & Multi-Filters:** Filter by keyword, category, date, and venue.

---

## 🛠️ Local Development Setup

### 1. Prerequisites
- Python 3.11+ (Python 3.12 recommended)
- Git

### 2. Clone Repository & Install Dependencies
```bash
git clone https://github.com/your-username/EventSphere.git
cd EventSphere

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file (optional, defaults provided):
```env
SECRET_KEY=eventsphere-super-secure-key-2026
DATABASE_URL=sqlite:///./eventsphere.db
PORT=8000
```

### 4. Seed Database with Demo Accounts & Venues
```bash
python scripts/seed_data.py
```

### 5. Run the Local Server
```bash
python scripts/run.py
# Or directly via uvicorn:
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **`http://127.0.0.1:8000`** in your browser (or mobile device via LAN).

---

## 🧪 Running Pytest Tests

EventSphere includes **17 comprehensive tests** covering overbooking race conditions, double check-in prevention, turnaround buffer clashes, and every individual agent:

```bash
python -m pytest tests/ -v -W ignore::DeprecationWarning
```

### Test Coverage Highlights:
- `test_venue_agent_turnaround_buffer_clash`: Verifies 60-min turnaround buffer rejection.
- `test_venue_agent_capacity_limit`: Verifies venue capacity enforcement.
- `test_booking_agent_quantity_limit`: Verifies max 6 tickets limit.
- `test_prevent_overselling_concurrency`: Verifies that concurrent attempts to claim the last seat never oversell.
- `test_cart_hold_reservation_concurrency`: Verifies temporary cart reservation locking.
- `test_ticket_scanner_double_checkin_rejection`: Verifies single admission enforcement.
- `test_ticket_scanner_fraud_alert_rapid_scans`: Verifies rapid scan fraud detection within 30s.
- `test_ticket_scanner_wrong_event_rejection`: Verifies rejection of tickets presented at the wrong event gate.
- `test_venue_hire_counter_proposal_on_clash`: Verifies smart alternative generation.
- `test_venue_hire_escalation_high_occupancy`: Verifies $>80\%$ capacity escalation.
- `test_waitlist_reactive_seat_release`: Verifies reactive seat release on cancellation.
- `test_waitlist_proactive_sweep_expiry`: Verifies proactive scheduler sweep without user input.
- `test_booking_refund_policy_rules`: Verifies 100%, 50%, and 0% refund tiers.
- `test_notification_agent_listener`: Verifies broadcast event delivery.
- `test_message_bus_traceability`: Verifies audit logging of conversation IDs.

---

## 📦 Cloud Deployment (Render / Docker)

### Deploying to Render
1. Push your repository to GitHub.
2. In Render, select **New Web Service** and connect your GitHub repository.
3. Configure:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt && python scripts/seed_data.py`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Deploy! Your app will be accessible over public HTTPS.

### Deploying with Docker
```bash
docker build -t eventsphere .
docker run -p 8000:8000 eventsphere
```
Or with Docker Compose:
```bash
docker-compose up -d
```
