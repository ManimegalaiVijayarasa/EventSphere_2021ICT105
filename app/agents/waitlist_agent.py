from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.agents.base import BaseAgent, Performative
from app.config import settings
from app.models import WaitlistEntry, TicketCategory, Event, User
from app.schemas import AgentMessage

class WaitlistAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="WaitlistAgent",
            goal="Pass freed seats to waiting customers, hold them for a time limit, and automatically re-offer expired holds."
        )

    def process_message(self, message: AgentMessage, db: Session) -> Optional[AgentMessage]:
        action = message.content.get("action")

        # Reactive trigger: Reaction to broadcast/direct INFORM from BookingAgent
        if message.performative == Performative.INFORM:
            if action == "SEATS_FREED":
                return self._handle_seats_freed(message, db)

        elif message.performative == Performative.REQUEST:
            if action == "JOIN_WAITLIST":
                return self._handle_join_waitlist(message, db)
            elif action == "PROACTIVE_SWEEP":
                return self._handle_proactive_sweep(message, db)
            elif action == "CLAIM_SEAT":
                return self._handle_claim_seat(message, db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.REFUSE,
            content={"reason": f"WaitlistAgent: Unsupported action '{action}'."},
            conversation_id=message.conversation_id
        )

    def _handle_join_waitlist(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        event_id = content.get("event_id")
        category_id = content.get("ticket_category_id")
        requested_quantity = content.get("requested_quantity", 1)

        # Check existing active waitlist entry
        existing = db.query(WaitlistEntry).filter(
            WaitlistEntry.user_id == user_id,
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.ticket_category_id == category_id,
            WaitlistEntry.status.in_(["waiting", "offered"])
        ).first()

        if existing:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"You are already on the waitlist for this category (Status: {existing.status})."},
                conversation_id=message.conversation_id
            )

        entry = WaitlistEntry(
            user_id=user_id,
            event_id=event_id,
            ticket_category_id=category_id,
            requested_quantity=requested_quantity,
            status="waiting"
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)

        # Count position in queue
        position = db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.ticket_category_id == category_id,
            WaitlistEntry.status == "waiting",
            WaitlistEntry.id <= entry.id
        ).count()

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "waitlist_id": entry.id,
                "status": "waiting",
                "queue_position": position,
                "message": f"Successfully joined waitlist at position #{position}."
            },
            conversation_id=message.conversation_id
        )

    def _offer_seat_to_next(self, event_id: int, category_id: int, freed_quantity: int, db: Session, conversation_id: str) -> int:
        """Finds next eligible attendees in queue and offers timed holds."""
        allocated = 0
        now = datetime.utcnow()

        waiting_candidates = db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.ticket_category_id == category_id,
            WaitlistEntry.status == "waiting"
        ).order_by(WaitlistEntry.created_at.asc()).all()

        for candidate in waiting_candidates:
            if candidate.requested_quantity <= freed_quantity:
                candidate.status = "offered"
                candidate.offer_expires_at = now + timedelta(minutes=settings.WAITLIST_HOLD_DURATION_MINUTES)
                freed_quantity -= candidate.requested_quantity
                allocated += candidate.requested_quantity

                # Notify user of seat offer with visible countdown
                if self.bus:
                    notify_msg = self.build_message(
                        receiver="NotificationAgent",
                        performative=Performative.INFORM,
                        content={
                            "event_type": "WAITLIST_SEAT_OFFERED",
                            "user_id": candidate.user_id,
                            "waitlist_id": candidate.id,
                            "event_title": candidate.event.title,
                            "category_name": candidate.ticket_category_id,
                            "quantity": candidate.requested_quantity,
                            "expires_at": candidate.offer_expires_at.isoformat(),
                            "duration_minutes": settings.WAITLIST_HOLD_DURATION_MINUTES
                        },
                        conversation_id=conversation_id
                    )
                    self.bus.send(notify_msg, db=db)

            if freed_quantity <= 0:
                break

        db.commit()
        return allocated

    def _handle_seats_freed(self, message: AgentMessage, db: Session) -> AgentMessage:
        """Reactive behaviour triggered when BookingAgent releases seats."""
        content = message.content
        event_id = content.get("event_id")
        category_id = content.get("ticket_category_id")
        freed_qty = content.get("freed_quantity", 1)

        allocated_qty = self._offer_seat_to_next(event_id, category_id, freed_qty, db, message.conversation_id)

        # Update persistent belief
        total_offered = self.get_belief(db, "total_waitlist_seats_offered", 0) + allocated_qty
        self.set_belief(db, "total_waitlist_seats_offered", total_offered)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.INFORM,
            content={
                "event_id": event_id,
                "category_id": category_id,
                "freed_quantity": freed_qty,
                "allocated_to_waitlist": allocated_qty
            },
            conversation_id=message.conversation_id
        )

    def _handle_proactive_sweep(self, message: AgentMessage, db: Session) -> AgentMessage:
        """Proactive behaviour: runs periodically on a timer without any user input."""
        now = datetime.utcnow()

        # Find all expired holds
        expired_offers = db.query(WaitlistEntry).filter(
            WaitlistEntry.status == "offered",
            WaitlistEntry.offer_expires_at < now
        ).all()

        reoffered_count = 0
        returned_to_public_count = 0

        for entry in expired_offers:
            entry.status = "expired"
            db.commit()

            # Attempt to re-offer to next waiting customer
            allocated = self._offer_seat_to_next(
                entry.event_id,
                entry.ticket_category_id,
                entry.requested_quantity,
                db,
                message.conversation_id
            )
            reoffered_count += allocated

            # If no waiting customers remain, return unallocated seats back to public capacity
            leftover = entry.requested_quantity - allocated
            if leftover > 0:
                category = db.query(TicketCategory).filter(TicketCategory.id == entry.ticket_category_id).first()
                if category:
                    category.available_quantity += leftover
                    returned_to_public_count += leftover
                db.commit()

            # Notify user that their hold expired
            if self.bus:
                self.bus.send(self.build_message(
                    receiver="NotificationAgent",
                    performative=Performative.INFORM,
                    content={
                        "event_type": "WAITLIST_OFFER_EXPIRED",
                        "user_id": entry.user_id,
                        "event_title": entry.event.title,
                        "waitlist_id": entry.id
                    },
                    conversation_id=message.conversation_id
                ), db=db)

        # Track proactive sweep stats in beliefs
        sweep_stats = self.get_belief(db, "waitlist_sweep_stats", {"last_run": None, "total_sweeps": 0})
        sweep_stats["last_run"] = now.isoformat()
        sweep_stats["total_sweeps"] = sweep_stats.get("total_sweeps", 0) + 1
        self.set_belief(db, "waitlist_sweep_stats", sweep_stats)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.INFORM,
            content={
                "expired_count": len(expired_offers),
                "reoffered_count": reoffered_count,
                "returned_to_public": returned_to_public_count,
                "timestamp": now.isoformat()
            },
            conversation_id=message.conversation_id
        )

    def _handle_claim_seat(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        waitlist_id = content.get("waitlist_id")

        entry = db.query(WaitlistEntry).filter(
            WaitlistEntry.id == waitlist_id,
            WaitlistEntry.user_id == user_id
        ).first()

        if not entry:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Waitlist entry #{waitlist_id} not found."},
                conversation_id=message.conversation_id
            )

        if entry.status != "offered":
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Cannot claim seat in state '{entry.status}'. Must be in 'offered' state."},
                conversation_id=message.conversation_id
            )

        if entry.offer_expires_at < datetime.utcnow():
            entry.status = "expired"
            db.commit()
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": "Seat offer has expired. The seat has been passed to the next person."},
                conversation_id=message.conversation_id
            )

        # Mark as claimed and convert to booking
        entry.status = "claimed"
        db.commit()

        # Send request to BookingAgent to confirm booking
        booking_result = None
        if self.bus:
            book_req = self.build_message(
                receiver="BookingAgent",
                performative=Performative.REQUEST,
                content={
                    "action": "CONFIRM_BOOKING",
                    "user_id": user_id,
                    "event_id": entry.event_id,
                    "ticket_category_id": entry.ticket_category_id,
                    "quantity": entry.requested_quantity
                },
                conversation_id=message.conversation_id
            )
            book_reply = self.bus.send(book_req, db=db)
            if book_reply.performative == Performative.AGREE:
                booking_result = book_reply.content

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "status": "claimed",
                "waitlist_id": entry.id,
                "booking_details": booking_result
            },
            conversation_id=message.conversation_id
        )
