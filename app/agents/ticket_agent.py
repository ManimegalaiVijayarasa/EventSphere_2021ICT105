import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent, Performative
from app.config import settings
from app.models import Ticket, Booking, Event, User
from app.schemas import AgentMessage

class TicketAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="TicketAgent",
            goal="Issue unguessable digital tickets and ensure each ticket is admitted exactly once."
        )

    def process_message(self, message: AgentMessage, db: Session) -> Optional[AgentMessage]:
        action = message.content.get("action")

        if message.performative == Performative.REQUEST:
            if action == "ISSUE_TICKETS":
                return self._handle_issue_tickets(message, db)
            elif action == "VALIDATE_SCAN":
                return self._handle_validate_scan(message, db)
            elif action == "INVALIDATE_BOOKING_TICKETS":
                return self._handle_invalidate_tickets(message, db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.REFUSE,
            content={"reason": f"TicketAgent: Unsupported action '{action}'."},
            conversation_id=message.conversation_id
        )

    def _generate_unguessable_code(self) -> str:
        # High-entropy, URL-safe cryptographic token
        token = secrets.token_urlsafe(16).upper().replace("_", "").replace("-", "")
        return f"TK-{token[:16]}"

    def _handle_issue_tickets(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        booking_id = content.get("booking_id")
        quantity = content.get("quantity", 1)

        codes = []
        for _ in range(quantity):
            code = self._generate_unguessable_code()
            ticket = Ticket(
                booking_id=booking_id,
                ticket_code=code,
                status="valid",
                scan_count=0
            )
            db.add(ticket)
            codes.append(code)

        db.commit()

        # Update persistent belief: total tickets issued counter
        current_total = self.get_belief(db, "total_tickets_issued", 0)
        self.set_belief(db, "total_tickets_issued", current_total + quantity)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "booking_id": booking_id,
                "quantity": quantity,
                "ticket_codes": codes
            },
            conversation_id=message.conversation_id
        )

    def _handle_validate_scan(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        ticket_code = content.get("ticket_code", "").strip()
        current_event_id = content.get("event_id")
        staff_user_id = content.get("staff_user_id")

        now = datetime.utcnow()

        ticket = db.query(Ticket).filter(Ticket.ticket_code == ticket_code).first()
        if not ticket:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "admit": False,
                    "status": "NOT_FOUND",
                    "reason": "Invalid ticket code: No matching ticket found in system.",
                    "ticket_code": ticket_code
                },
                conversation_id=message.conversation_id
            )

        booking = ticket.booking
        event = booking.event
        attendee = booking.user

        # Decision 1: Ticket was cancelled / refunded
        if ticket.status == "cancelled" or booking.status in ["cancelled", "refunded"]:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "admit": False,
                    "status": "CANCELLED",
                    "reason": "Admission rejected: This ticket has been cancelled or refunded.",
                    "ticket_code": ticket_code,
                    "event_title": event.title,
                    "attendee_name": attendee.full_name
                },
                conversation_id=message.conversation_id
            )

        # Decision 2: Wrong event validation
        if current_event_id and event.id != current_event_id:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "admit": False,
                    "status": "WRONG_EVENT",
                    "reason": f"Admission rejected: Ticket is for '{event.title}', not this event.",
                    "ticket_code": ticket_code,
                    "event_title": event.title,
                    "attendee_name": attendee.full_name
                },
                conversation_id=message.conversation_id
            )

        # Decision 3: Check-in window validation (2 hours before event start to event end)
        checkin_open = event.start_time - timedelta(hours=2)
        checkin_close = event.end_time + timedelta(hours=1)
        if now < checkin_open or now > checkin_close:
            window_msg = (
                f"Check-in opens {checkin_open.strftime('%Y-%m-%d %H:%M')} and closes {checkin_close.strftime('%H:%M')}."
            )
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "admit": False,
                    "status": "OUTSIDE_CHECKIN_TIME",
                    "reason": f"Admission rejected: Outside designated check-in window. {window_msg}",
                    "ticket_code": ticket_code,
                    "event_title": event.title,
                    "attendee_name": attendee.full_name
                },
                conversation_id=message.conversation_id
            )

        # Decision 4: Already used / Duplicate scan detection & Suspicious Fraud Alert
        if ticket.status == "admitted":
            ticket.scan_count += 1
            last_scan = ticket.last_scanned_at or ticket.admitted_at

            is_suspicious = False
            if last_scan:
                diff_seconds = (now - last_scan).total_seconds()
                if diff_seconds < settings.SUSPICIOUS_SCAN_WINDOW_SECONDS:
                    is_suspicious = True

            ticket.last_scanned_at = now
            db.commit()

            # Record fraud belief if suspicious
            if is_suspicious:
                fraud_count = self.get_belief(db, "suspicious_scans_detected", 0) + 1
                self.set_belief(db, "suspicious_scans_detected", fraud_count)

                return self.build_message(
                    receiver=message.sender,
                    performative=Performative.REFUSE,
                    content={
                        "admit": False,
                        "status": "FRAUD_ALERT",
                        "reason": f"SUSPICIOUS DUPLICATE SCAN! Scanned {ticket.scan_count} times in rapid succession ({int(diff_seconds)}s ago). Possible screenshot sharing!",
                        "ticket_code": ticket_code,
                        "admitted_at": ticket.admitted_at.isoformat() if ticket.admitted_at else None,
                        "scan_count": ticket.scan_count,
                        "event_title": event.title,
                        "attendee_name": attendee.full_name
                    },
                    conversation_id=message.conversation_id
                )

            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "admit": False,
                    "status": "ALREADY_USED",
                    "reason": f"Admission rejected: Ticket was already admitted at {ticket.admitted_at.strftime('%H:%M:%S') if ticket.admitted_at else 'earlier'}.",
                    "ticket_code": ticket_code,
                    "admitted_at": ticket.admitted_at.isoformat() if ticket.admitted_at else None,
                    "scan_count": ticket.scan_count,
                    "event_title": event.title,
                    "attendee_name": attendee.full_name
                },
                conversation_id=message.conversation_id
            )

        # Decision 5: Valid admission!
        ticket.status = "admitted"
        ticket.admitted_at = now
        ticket.last_scanned_at = now
        ticket.scan_count = 1
        ticket.check_in_by_user_id = staff_user_id
        db.commit()

        # Update persistent belief
        admitted_total = self.get_belief(db, "total_tickets_admitted", 0) + 1
        self.set_belief(db, "total_tickets_admitted", admitted_total)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "admit": True,
                "status": "ADMITTED",
                "reason": f"Admitted successfully! Welcome, {attendee.full_name}.",
                "ticket_code": ticket_code,
                "event_title": event.title,
                "attendee_name": attendee.full_name,
                "ticket_category": booking.ticket_category.name,
                "admitted_at": now.isoformat(),
                "scan_count": 1
            },
            conversation_id=message.conversation_id
        )

    def _handle_invalidate_tickets(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        booking_id = content.get("booking_id")

        tickets = db.query(Ticket).filter(Ticket.booking_id == booking_id).all()
        for t in tickets:
            t.status = "cancelled"
        db.commit()

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"booking_id": booking_id, "invalidated_count": len(tickets)},
            conversation_id=message.conversation_id
        )
