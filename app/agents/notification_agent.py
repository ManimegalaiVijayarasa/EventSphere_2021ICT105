import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.agents.base import BaseAgent, Performative
from app.models import Notification, User
from app.schemas import AgentMessage

logger = logging.getLogger("eventsphere.notification_agent")

class NotificationAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="NotificationAgent",
            goal="Tell the right person what affects them through in-app and simulated email channels."
        )

    def process_message(self, message: AgentMessage, db: Session) -> Optional[AgentMessage]:
        # Listens to INFORM performatives from other agents
        if message.performative == Performative.INFORM:
            return self._handle_inform_event(message, db)
        elif message.performative == Performative.REQUEST:
            if message.content.get("action") == "SEND_DIRECT_ALERT":
                return self._handle_direct_alert(message, db)

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"status": "received_and_ignored"},
            conversation_id=message.conversation_id
        )

    def _create_notification(self, db: Session, user_id: int, title: str, text: str, channel: str = "in_app"):
        notif = Notification(
            user_id=user_id,
            title=title,
            message=text,
            channel=channel,
            is_read=False
        )
        db.add(notif)
        db.commit()

        # Update persistent delivery counters
        counter = self.get_belief(db, f"notif_count_{channel}", 0) + 1
        self.set_belief(db, f"notif_count_{channel}", counter)

        # Simulated Email Dispatch log
        logger.info(f"[{channel.upper()}] To User #{user_id} | Title: {title} | Body: {text}")

    def _handle_inform_event(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        event_type = content.get("event_type")
        user_id = content.get("user_id")

        if not user_id:
            # If notification is for all admins
            if event_type == "HIRE_ESCALATED":
                admin_users = db.query(User).filter(User.role == "admin").all()
                for admin in admin_users:
                    self._create_notification(
                        db=db,
                        user_id=admin.id,
                        title="Private Venue Hire Escalated",
                        text=f"A private hire for '{content.get('venue_name')}' requires organizer approval. Reason: {content.get('reason')}. Price: ${content.get('total_price')}.",
                        channel="in_app"
                    )
                return self.build_message(
                    receiver=message.sender,
                    performative=Performative.AGREE,
                    content={"status": "admin_notifications_dispatched"},
                    conversation_id=message.conversation_id
                )
            return self.build_message(
                receiver=message.sender,
                performative=Performative.REFUSE,
                content={"reason": "No user_id supplied for notification."},
                conversation_id=message.conversation_id
            )

        # Handle Attendee Notification Types:
        if event_type == "TICKET_BOOKED":
            title = f"Tickets Confirmed: {content.get('event_title')}"
            body = (
                f"Your booking for {content.get('quantity')} ticket(s) is confirmed! "
                f"Simulated payment reference: {content.get('payment_reference')}. "
                f"Total: ${content.get('total_amount')}."
            )
            self._create_notification(db, user_id, title, body, channel="in_app")
            self._create_notification(db, user_id, title, body, channel="email")

        elif event_type == "BOOKING_CANCELLED":
            title = "Booking Cancellation & Refund Notice"
            body = (
                f"Your booking #{content.get('booking_id')} has been cancelled. "
                f"Refund of ${content.get('refund_amount')} has been credited ({content.get('policy_reason')})."
            )
            self._create_notification(db, user_id, title, body, channel="in_app")
            self._create_notification(db, user_id, title, body, channel="email")

        elif event_type == "EVENT_CANCELLED_REFUND":
            title = "Event Cancelled by Organiser - Full Refund"
            body = (
                f"An event you booked was cancelled by the organiser. "
                f"A full 100% refund of ${content.get('refund_amount')} has been processed to your payment reference."
            )
            self._create_notification(db, user_id, title, body, channel="in_app")
            self._create_notification(db, user_id, title, body, channel="email")

        elif event_type == "HIRE_CONFIRMED":
            title = "Private Venue Hire Confirmed"
            body = (
                f"Your routine private hire for '{content.get('venue_name')}' is automatically confirmed! "
                f"Total hire fee: ${content.get('total_price')}."
            )
            self._create_notification(db, user_id, title, body, channel="in_app")
            self._create_notification(db, user_id, title, body, channel="email")

        elif event_type == "HIRE_ESCALATED":
            title = "Venue Hire Under Review"
            body = (
                f"Your hire request for '{content.get('venue_name')}' was escalated for organiser review: "
                f"{content.get('reason')}."
            )
            self._create_notification(db, user_id, title, body, channel="in_app")

        elif event_type == "HIRE_ADMIN_DECISION":
            decision = content.get("decision")
            notes = content.get("notes") or "No additional notes."
            title = f"Venue Hire {decision.capitalize()}"
            body = f"Your private venue hire #{content.get('hire_id')} was {decision} by the organiser. Notes: {notes}."
            self._create_notification(db, user_id, title, body, channel="in_app")
            self._create_notification(db, user_id, title, body, channel="email")

        elif event_type == "WAITLIST_SEAT_OFFERED":
            title = "Seats Released: Claim Your Tickets!"
            body = (
                f"Good news! {content.get('quantity')} seat(s) for '{content.get('event_title')}' have become available! "
                f"You have {content.get('duration_minutes')} minutes to claim them before they are offered to the next attendee."
            )
            self._create_notification(db, user_id, title, body, channel="in_app")
            self._create_notification(db, user_id, title, body, channel="email")

        elif event_type == "WAITLIST_OFFER_EXPIRED":
            title = "Waitlist Seat Hold Expired"
            body = f"Your timed hold for '{content.get('event_title')}' has expired and passed to the next person on the waitlist."
            self._create_notification(db, user_id, title, body, channel="in_app")

        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"status": "notified", "event_type": event_type, "user_id": user_id},
            conversation_id=message.conversation_id
        )

    def _handle_direct_alert(self, message: AgentMessage, db: Session) -> AgentMessage:
        content = message.content
        user_id = content.get("user_id")
        title = content.get("title", "EventSphere Notification")
        text = content.get("text", "")
        self._create_notification(db, user_id, title, text, channel="in_app")
        return self.build_message(
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"status": "delivered"},
            conversation_id=message.conversation_id
        )
