from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.agents.base import BaseAgent, Performative
from app.config import settings
from app.models import Venue, Event, VenueHire
from app.schemas import AgentMessage

class VenueAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="VenueAgent",
            goal="Keep every venue's calendar free of clashes and manage venue reservations."
        )

    def process_message(self, message: AgentMessage, db: Session) -> Optional[AgentMessage]:
        action = message.content.get("action")

        if message.performative == Performative.REQUEST:
            if action == "CHECK_EVENT_SLOT":
                return self._handle_check_event_slot(message, db)
            elif action == "REQUEST_VENUE_HIRE":
                return self._handle_private_hire_request(message, db)
            elif action == "ADMIN_REVIEW_HIRE":
                return self._handle_admin_review_hire(message, db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.REFUSE,
            content={"reason": f"Unsupported performative '{message.performative}' or action '{action}'."},
            conversation_id=message.conversation_id
        )

    def _is_slot_conflicting(
        self,
        venue_id: int,
        start_time: datetime,
        end_time: datetime,
        exclude_event_id: Optional[int],
        db: Session,
        include_buffer: bool = True
    ) -> (bool, str):
        buffer_minutes = settings.VENUE_TURNAROUND_BUFFER_MINUTES if include_buffer else 0
        buffered_start = start_time - timedelta(minutes=buffer_minutes)
        buffered_end = end_time + timedelta(minutes=buffer_minutes)

        # 1. Check clash against existing published/draft events
        event_query = db.query(Event).filter(
            Event.venue_id == venue_id,
            Event.status.in_(["published", "draft"]),
            Event.start_time < buffered_end,
            Event.end_time > buffered_start
        )
        if exclude_event_id:
            event_query = event_query.filter(Event.id != exclude_event_id)

        clashing_event = event_query.first()
        if clashing_event:
            return True, f"Clashes with event '{clashing_event.title}' ({clashing_event.start_time.strftime('%Y-%m-%d %H:%M')} to {clashing_event.end_time.strftime('%H:%M')}) including {buffer_minutes}m turnaround buffer."

        # 2. Check clash against confirmed/approved private venue hires
        clashing_hire = db.query(VenueHire).filter(
            VenueHire.venue_id == venue_id,
            VenueHire.status.in_(["confirmed", "approved"]),
            VenueHire.start_time < buffered_end,
            VenueHire.end_time > buffered_start
        ).first()

        if clashing_hire:
            return True, f"Clashes with private hire #{clashing_hire.id} ({clashing_hire.start_time.strftime('%Y-%m-%d %H:%M')} to {clashing_hire.end_time.strftime('%H:%M')}) including {buffer_minutes}m turnaround buffer."

        return False, ""

    def _calculate_hire_price(self, hourly_rate: float, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        duration_hours = max((end_time - start_time).total_seconds() / 3600.0, 1.0)
        base_price = duration_hours * hourly_rate
        multiplier = 1.0
        reasons = []

        # Weekend pricing (Saturday = 5, Sunday = 6)
        if start_time.weekday() in (5, 6):
            multiplier *= settings.WEEKEND_PRICE_MULTIPLIER
            reasons.append(f"Weekend rate ({settings.WEEKEND_PRICE_MULTIPLIER}x)")

        # Peak hours pricing (18:00 - 22:00)
        if not (end_time.hour < settings.PEAK_HOUR_START or start_time.hour >= settings.PEAK_HOUR_END):
            multiplier *= settings.PEAK_HOUR_MULTIPLIER
            reasons.append(f"Peak evening rate ({settings.PEAK_HOUR_MULTIPLIER}x)")

        final_price = round(base_price * multiplier, 2)
        return {
            "duration_hours": round(duration_hours, 2),
            "base_rate": hourly_rate,
            "multiplier": round(multiplier, 2),
            "reasons": reasons,
            "final_price": final_price
        }

    def _handle_check_event_slot(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        venue_id = content.get("venue_id")
        start_time = datetime.fromisoformat(content.get("start_time")) if isinstance(content.get("start_time"), str) else content.get("start_time")
        end_time = datetime.fromisoformat(content.get("end_time")) if isinstance(content.get("end_time"), str) else content.get("end_time")
        exclude_event_id = content.get("exclude_event_id")
        total_tickets = content.get("total_tickets", 0)

        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Venue #{venue_id} does not exist."},
                conversation_id=message.conversation_id
            )

        if total_tickets > venue.capacity:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "reason": f"Total tickets ({total_tickets}) exceeds venue capacity ({venue.capacity})."
                },
                conversation_id=message.conversation_id
            )

        is_conflict, reason = self._is_slot_conflicting(venue_id, start_time, end_time, exclude_event_id, db)
        if is_conflict:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": reason},
                conversation_id=message.conversation_id
            )

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"status": "AVAILABLE", "venue_name": venue.name, "capacity": venue.capacity},
            conversation_id=message.conversation_id
        )

    def _handle_private_hire_request(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        venue_id = content.get("venue_id")
        start_time = datetime.fromisoformat(content.get("start_time")) if isinstance(content.get("start_time"), str) else content.get("start_time")
        end_time = datetime.fromisoformat(content.get("end_time")) if isinstance(content.get("end_time"), str) else content.get("end_time")
        purpose = content.get("purpose", "").strip()
        guest_count = content.get("guest_count", 1)

        venue = db.query(Venue).filter(Venue.id == venue_id).first()
        if not venue:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Venue #{venue_id} not found."},
                conversation_id=message.conversation_id
            )

        if not venue.is_open_for_hire:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Venue '{venue.name}' is currently closed for private hire."},
                conversation_id=message.conversation_id
            )

        if guest_count > venue.capacity:
            # Look for alternative venues that fit guest count
            alt_venues = db.query(Venue).filter(
                Venue.is_open_for_hire == True,
                Venue.capacity >= guest_count,
                Venue.id != venue.id
            ).all()

            proposals = []
            for alt in alt_venues:
                conflict, _ = self._is_slot_conflicting(alt.id, start_time, end_time, None, db)
                if not conflict:
                    pricing = self._calculate_hire_price(alt.hourly_hire_rate, start_time, end_time)
                    proposals.append({
                        "type": "alternative_venue",
                        "venue_id": alt.id,
                        "venue_name": alt.name,
                        "capacity": alt.capacity,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "total_price": pricing["final_price"]
                    })

            return self.build_message(
                receiver=message.sender,
                performative=Performative.PROPOSE,
                content={
                    "reason": f"Guest count ({guest_count}) exceeds venue capacity ({venue.capacity}).",
                    "alternatives": proposals
                },
                conversation_id=message.conversation_id
            )

        # Check for slot conflicts
        is_conflict, conflict_reason = self._is_slot_conflicting(venue_id, start_time, end_time, None, db)
        if is_conflict:
            # Requirement: Offer alternative times or venues instead of only refusing
            duration = end_time - start_time
            alternatives = []

            # 1. Alternative time slot: 3 hours later on same day
            alt_start_1 = end_time + timedelta(minutes=settings.VENUE_TURNAROUND_BUFFER_MINUTES)
            alt_end_1 = alt_start_1 + duration
            conflict_1, _ = self._is_slot_conflicting(venue_id, alt_start_1, alt_end_1, None, db)
            if not conflict_1:
                pricing_1 = self._calculate_hire_price(venue.hourly_hire_rate, alt_start_1, alt_end_1)
                alternatives.append({
                    "type": "alternative_time",
                    "venue_id": venue.id,
                    "venue_name": venue.name,
                    "start_time": alt_start_1.isoformat(),
                    "end_time": alt_end_1.isoformat(),
                    "total_price": pricing_1["final_price"],
                    "description": f"Later slot on same day: {alt_start_1.strftime('%H:%M')} - {alt_end_1.strftime('%H:%M')}"
                })

            # 2. Alternative venues free at requested time
            other_venues = db.query(Venue).filter(
                Venue.is_open_for_hire == True,
                Venue.capacity >= guest_count,
                Venue.id != venue.id
            ).all()
            for ov in other_venues:
                c_other, _ = self._is_slot_conflicting(ov.id, start_time, end_time, None, db)
                if not c_other:
                    pricing_ov = self._calculate_hire_price(ov.hourly_hire_rate, start_time, end_time)
                    alternatives.append({
                        "type": "alternative_venue",
                        "venue_id": ov.id,
                        "venue_name": ov.name,
                        "capacity": ov.capacity,
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "total_price": pricing_ov["final_price"],
                        "description": f"Alternative venue '{ov.name}' (Cap: {ov.capacity})"
                    })

            return self.build_message(
                receiver=message.sender,
                performative=Performative.PROPOSE,
                content={
                    "reason": f"Requested slot at '{venue.name}' is unavailable ({conflict_reason}).",
                    "alternatives": alternatives
                },
                conversation_id=message.conversation_id
            )

        # Slot is available! Calculate pricing
        pricing = self._calculate_hire_price(venue.hourly_hire_rate, start_time, end_time)
        total_price = pricing["final_price"]

        # Decision rule: Routine vs Escalated
        # Routine: guest_count <= 80% capacity AND not high-impact purpose
        high_impact_keywords = ["concert", "party", "rave", "reception", "farewell", "commercial", "fundraiser"]
        is_high_impact = any(k in purpose.lower() for k in high_impact_keywords) and guest_count > 50
        is_high_occupancy = guest_count > (0.80 * venue.capacity)

        if is_high_impact or is_high_occupancy:
            # Escalate to admin
            escalation_reasons = []
            if is_high_occupancy:
                escalation_reasons.append(f"Guest count ({guest_count}) exceeds 80% capacity ({venue.capacity})")
            if is_high_impact:
                escalation_reasons.append(f"High-impact activity purpose: '{purpose}'")
            escalation_str = "; ".join(escalation_reasons)

            hire_record = VenueHire(
                user_id=user_id,
                venue_id=venue_id,
                start_time=start_time,
                end_time=end_time,
                purpose=purpose,
                guest_count=guest_count,
                total_price=total_price,
                status="escalated",
                escalation_reason=escalation_str
            )
            db.add(hire_record)
            db.commit()
            db.refresh(hire_record)

            # Inform NotificationAgent to alert admin and attendee
            if self.bus:
                notify_msg = self.build_message(
                    receiver="NotificationAgent",
                    performative=Performative.INFORM,
                    content={
                        "event_type": "HIRE_ESCALATED",
                        "user_id": user_id,
                        "hire_id": hire_record.id,
                        "venue_name": venue.name,
                        "reason": escalation_str,
                        "total_price": total_price
                    },
                    conversation_id=message.conversation_id
                )
                self.bus.send(notify_msg, db=db)

            return self.build_message(
                receiver=message.sender,
                performative=Performative.PROPOSE,
                content={
                    "hire_id": hire_record.id,
                    "status": "ESCALATED",
                    "total_price": total_price,
                    "pricing_details": pricing,
                    "reason": f"Routine threshold exceeded ({escalation_str}). Escalated to organizer for human approval."
                },
                conversation_id=message.conversation_id
            )

        # Routine request -> Automatically confirmed!
        hire_record = VenueHire(
            user_id=user_id,
            venue_id=venue_id,
            start_time=start_time,
            end_time=end_time,
            purpose=purpose,
            guest_count=guest_count,
            total_price=total_price,
            status="confirmed"
        )
        db.add(hire_record)
        db.commit()
        db.refresh(hire_record)

        # Notify attendee of instant confirmation
        if self.bus:
            notify_msg = self.build_message(
                receiver="NotificationAgent",
                performative=Performative.INFORM,
                content={
                    "event_type": "HIRE_CONFIRMED",
                    "user_id": user_id,
                    "hire_id": hire_record.id,
                    "venue_name": venue.name,
                    "total_price": total_price
                },
                conversation_id=message.conversation_id
            )
            self.bus.send(notify_msg, db=db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "hire_id": hire_record.id,
                "status": "CONFIRMED",
                "total_price": total_price,
                "pricing_details": pricing,
                "reason": "Routine hire request validated and automatically confirmed."
            },
            conversation_id=message.conversation_id
        )

    def _handle_admin_review_hire(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        hire_id = content.get("hire_id")
        decision = content.get("decision")  # approved or rejected
        notes = content.get("admin_notes", "")

        hire = db.query(VenueHire).filter(VenueHire.id == hire_id).first()
        if not hire:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"VenueHire #{hire_id} not found."},
                conversation_id=message.conversation_id
            )

        if decision == "approved":
            hire.status = "approved"
        else:
            hire.status = "rejected"
            hire.escalation_reason = (hire.escalation_reason or "") + f" [Admin Rejection: {notes}]"

        db.commit()

        # Notify attendee
        if self.bus:
            notify_msg = self.build_message(
                receiver="NotificationAgent",
                performative=Performative.INFORM,
                content={
                    "event_type": "HIRE_ADMIN_DECISION",
                    "user_id": hire.user_id,
                    "hire_id": hire.id,
                    "decision": hire.status,
                    "notes": notes
                },
                conversation_id=message.conversation_id
            )
            self.bus.send(notify_msg, db=db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"hire_id": hire.id, "new_status": hire.status},
            conversation_id=message.conversation_id
        )
