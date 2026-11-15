import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.agents.base import BaseAgent, Performative
from app.config import settings
from app.models import Event, TicketCategory, Booking, Ticket, CartHold
from app.schemas import AgentMessage

class BookingAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="BookingAgent",
            goal="Sell tickets fairly without overselling, manage cart holds, and process refunds."
        )

    def process_message(self, message: AgentMessage, db: Session) -> Optional[AgentMessage]:
        action = message.content.get("action")

        if message.performative == Performative.REQUEST:
            if action == "HOLD_CART":
                return self._handle_hold_cart(message, db)
            elif action == "CONFIRM_BOOKING":
                return self._handle_confirm_booking(message, db)
            elif action == "CANCEL_BOOKING":
                return self._handle_cancel_booking(message, db)
            elif action == "CANCEL_EVENT_REFUNDS":
                return self._handle_cancel_event_refunds(message, db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.REFUSE,
            content={"reason": f"BookingAgent: Unsupported action '{action}'."},
            conversation_id=message.conversation_id
        )

    def _handle_hold_cart(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        event_id = content.get("event_id")
        category_id = content.get("ticket_category_id")
        quantity = content.get("quantity", 1)

        # Rule 1: Quantity limits
        if quantity < 1 or quantity > settings.MAX_TICKETS_PER_BOOKING:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Quantity must be between 1 and {settings.MAX_TICKETS_PER_BOOKING} tickets."},
                conversation_id=message.conversation_id
            )

        # Rule 2: Event status check
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event or event.status != "published":
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": "Event is not published or does not exist."},
                conversation_id=message.conversation_id
            )

        # Rule 3: Event timing check (must be in the future)
        if event.start_time <= datetime.utcnow():
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": "Cannot book tickets for past or already started events."},
                conversation_id=message.conversation_id
            )

        # Rule 4: Concurrency-safe capacity check considering active cart holds
        category = db.query(TicketCategory).filter(
            TicketCategory.id == category_id,
            TicketCategory.event_id == event_id
        ).with_for_update().first()

        if not category:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Ticket category #{category_id} not found."},
                conversation_id=message.conversation_id
            )

        # Calculate currently active holds
        now = datetime.utcnow()
        active_holds_qty = db.query(func.coalesce(func.sum(CartHold.quantity), 0)).filter(
            CartHold.ticket_category_id == category_id,
            CartHold.status == "active",
            CartHold.expires_at > now
        ).scalar() or 0

        effective_available = category.available_quantity - active_holds_qty
        if effective_available < quantity:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={
                    "reason": f"Insufficient seats available. Requested {quantity}, but only {max(0, effective_available)} seats remain.",
                    "available_seats": max(0, effective_available),
                    "can_join_waitlist": True
                },
                conversation_id=message.conversation_id
            )

        # Create cart hold
        expires_at = now + timedelta(minutes=settings.CART_HOLD_DURATION_MINUTES)
        cart_hold = CartHold(
            user_id=user_id,
            event_id=event_id,
            ticket_category_id=category_id,
            quantity=quantity,
            expires_at=expires_at,
            status="active"
        )
        db.add(cart_hold)
        db.commit()
        db.refresh(cart_hold)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "cart_hold_id": cart_hold.id,
                "expires_at": expires_at.isoformat(),
                "duration_minutes": settings.CART_HOLD_DURATION_MINUTES,
                "quantity": quantity,
                "total_price": round(category.price * quantity, 2)
            },
            conversation_id=message.conversation_id
        )

    def _handle_confirm_booking(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        event_id = content.get("event_id")
        category_id = content.get("ticket_category_id")
        quantity = content.get("quantity", 1)
        cart_hold_id = content.get("cart_hold_id")

        category = db.query(TicketCategory).filter(
            TicketCategory.id == category_id,
            TicketCategory.event_id == event_id
        ).with_for_update().first()

        if not category:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": "Ticket category not found."},
                conversation_id=message.conversation_id
            )

        # Check cart hold validity if provided
        now = datetime.utcnow()
        if cart_hold_id:
            hold = db.query(CartHold).filter(
                CartHold.id == cart_hold_id,
                CartHold.user_id == user_id,
                CartHold.status == "active"
            ).first()
            if not hold or hold.expires_at < now:
                return self.build_message(
                    receiver=message.sender,
                    performative=Performative.REFUSE,
                    content={"reason": "Cart hold has expired or is invalid. Please select tickets again."},
                    conversation_id=message.conversation_id
                )
            hold.status = "converted"
        else:
            # Direct checkout check
            if category.available_quantity < quantity:
                return self.build_message(
                    receiver=message.sender,
                    performative=Performative.REFUSE,
                    content={"reason": f"Only {category.available_quantity} seats available."},
                    conversation_id=message.conversation_id
                )

        # Deduct seats atomically
        category.available_quantity -= quantity
        total_amount = round(category.price * quantity, 2)
        payment_reference = f"PAY-SIM-{uuid.uuid4().hex[:10].upper()}"

        booking = Booking(
            user_id=user_id,
            event_id=event_id,
            ticket_category_id=category_id,
            quantity=quantity,
            total_amount=total_amount,
            payment_reference=payment_reference,
            status="confirmed"
        )
        db.add(booking)
        db.commit()
        db.refresh(booking)

        # Multi-Agent step: Request TicketAgent to generate unique unguessable digital tickets
        tickets_issued = []
        if self.bus:
            ticket_request = self.build_message(
                receiver="TicketAgent",
                performative=Performative.REQUEST,
                content={
                    "action": "ISSUE_TICKETS",
                    "booking_id": booking.id,
                    "quantity": quantity
                },
                conversation_id=message.conversation_id
            )
            ticket_reply = self.bus.send(ticket_request, db=db)
            if ticket_reply.performative == Performative.AGREE:
                tickets_issued = ticket_reply.content.get("ticket_codes", [])

        # Multi-Agent step: Inform NotificationAgent
        if self.bus:
            notify_msg = self.build_message(
                receiver="NotificationAgent",
                performative=Performative.INFORM,
                content={
                    "event_type": "TICKET_BOOKED",
                    "user_id": user_id,
                    "booking_id": booking.id,
                    "event_title": category.event.title,
                    "quantity": quantity,
                    "total_amount": total_amount,
                    "payment_reference": payment_reference
                },
                conversation_id=message.conversation_id
            )
            self.bus.send(notify_msg, db=db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "booking_id": booking.id,
                "status": "confirmed",
                "payment_reference": payment_reference,
                "total_amount": total_amount,
                "quantity": quantity,
                "ticket_codes": tickets_issued
            },
            conversation_id=message.conversation_id
        )

    def _handle_cancel_booking(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        booking_id = content.get("booking_id")

        booking = db.query(Booking).filter(
            Booking.id == booking_id,
            Booking.user_id == user_id
        ).first()

        if not booking:
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Booking #{booking_id} not found."},
                conversation_id=message.conversation_id
            )

        if booking.status != "confirmed":
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": f"Cannot cancel booking with status '{booking.status}'."},
                conversation_id=message.conversation_id
            )

        event = booking.event
        now = datetime.utcnow()
        hours_until_event = (event.start_time - now).total_seconds() / 3600.0

        # Stated Cancellation & Refund Policy:
        # > 48 hours: 100% refund
        # 24 - 48 hours: 50% refund
        # < 24 hours: 0% refund
        if hours_until_event >= settings.REFUND_FULL_HOURS:
            refund_rate = 1.0
            policy_reason = f"Cancelled more than {settings.REFUND_FULL_HOURS}h before event: 100% refund."
        elif hours_until_event >= settings.REFUND_PARTIAL_HOURS:
            refund_rate = settings.REFUND_PARTIAL_RATE
            policy_reason = f"Cancelled between {settings.REFUND_PARTIAL_HOURS}h and {settings.REFUND_FULL_HOURS}h before event: {int(settings.REFUND_PARTIAL_RATE*100)}% refund."
        else:
            refund_rate = 0.0
            policy_reason = f"Cancelled less than {settings.REFUND_PARTIAL_HOURS}h before event: 0% refund as per policy."

        refund_amount = round(booking.total_amount * refund_rate, 2)
        booking.status = "cancelled"
        booking.refund_amount = refund_amount

        # Restock tickets back to available capacity
        category = booking.ticket_category
        category.available_quantity += booking.quantity
        db.commit()

        # Multi-Agent step 1: Request TicketAgent to invalidate digital tickets
        if self.bus:
            ticket_msg = self.build_message(
                receiver="TicketAgent",
                performative=Performative.REQUEST,
                content={
                    "action": "INVALIDATE_BOOKING_TICKETS",
                    "booking_id": booking.id
                },
                conversation_id=message.conversation_id
            )
            self.bus.send(ticket_msg, db=db)

        # Multi-Agent step 2: Inform WaitlistAgent of freed seats
        if self.bus:
            waitlist_msg = self.build_message(
                receiver="WaitlistAgent",
                performative=Performative.INFORM,
                content={
                    "action": "SEATS_FREED",
                    "event_id": event.id,
                    "ticket_category_id": category.id,
                    "freed_quantity": booking.quantity
                },
                conversation_id=message.conversation_id
            )
            self.bus.send(waitlist_msg, db=db)

        # Multi-Agent step 3: Inform NotificationAgent
        if self.bus:
            notify_msg = self.build_message(
                receiver="NotificationAgent",
                performative=Performative.INFORM,
                content={
                    "event_type": "BOOKING_CANCELLED",
                    "user_id": user_id,
                    "booking_id": booking.id,
                    "refund_amount": refund_amount,
                    "policy_reason": policy_reason
                },
                conversation_id=message.conversation_id
            )
            self.bus.send(notify_msg, db=db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "booking_id": booking.id,
                "status": "cancelled",
                "refund_amount": refund_amount,
                "refund_rate": refund_rate,
                "policy_reason": policy_reason
            },
            conversation_id=message.conversation_id
        )

    def _handle_cancel_event_refunds(self, message: AgentMessage, db: Session) -> AgentMessage:
        """When an organiser cancels an event, full 100% refunds are issued automatically."""
        content = message.content
        event_id = content.get("event_id")

        bookings = db.query(Booking).filter(
            Booking.event_id == event_id,
            Booking.status == "confirmed"
        ).all()

        total_refunded = 0.0
        affected_users = []

        for b in bookings:
            b.status = "refunded"
            b.refund_amount = b.total_amount
            total_refunded += b.total_amount
            affected_users.append(b.user_id)

            # Invalidate tickets via TicketAgent
            if self.bus:
                self.bus.send(self.build_message(
                    receiver="TicketAgent",
                    performative=Performative.REQUEST,
                    content={"action": "INVALIDATE_BOOKING_TICKETS", "booking_id": b.id},
                    conversation_id=message.conversation_id
                ), db=db)

            # Notify user
            if self.bus:
                self.bus.send(self.build_message(
                    receiver="NotificationAgent",
                    performative=Performative.INFORM,
                    content={
                        "event_type": "EVENT_CANCELLED_REFUND",
                        "user_id": b.user_id,
                        "booking_id": b.id,
                        "refund_amount": b.total_amount,
                        "reason": "Event was cancelled by organiser. Full 100% refund processed."
                    },
                    conversation_id=message.conversation_id
                ), db=db)

        db.commit()

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={
                "event_id": event_id,
                "bookings_refunded": len(bookings),
                "total_refunded": round(total_refunded, 2)
            },
            conversation_id=message.conversation_id
        )
