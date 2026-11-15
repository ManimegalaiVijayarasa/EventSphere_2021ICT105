from app.agents.bus import agent_bus
from app.agents.venue_agent import VenueAgent
from app.agents.booking_agent import BookingAgent
from app.agents.ticket_agent import TicketAgent
from app.agents.waitlist_agent import WaitlistAgent
from app.agents.notification_agent import NotificationAgent

venue_agent = VenueAgent()
booking_agent = BookingAgent()
ticket_agent = TicketAgent()
waitlist_agent = WaitlistAgent()
notification_agent = NotificationAgent()

# Register all agents into the message bus
agent_bus.register_agent(venue_agent)
agent_bus.register_agent(booking_agent)
agent_bus.register_agent(ticket_agent)
agent_bus.register_agent(waitlist_agent)
agent_bus.register_agent(notification_agent)

__all__ = [
    "agent_bus",
    "venue_agent",
    "booking_agent",
    "ticket_agent",
    "waitlist_agent",
    "notification_agent"
]
