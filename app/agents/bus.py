import json
import logging
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import MessageLog
from app.schemas import AgentMessage
from app.agents.base import BaseAgent, Performative

logger = logging.getLogger("eventsphere.agent_bus")

class AgentMessageBus:
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent):
        self._agents[agent.name] = agent
        agent.set_bus(self)
        logger.info(f"Registered agent: {agent.name} (Goal: {agent.goal})")

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def _persist_message(self, db: Session, message: AgentMessage):
        log_entry = MessageLog(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sender=message.sender,
            receiver=message.receiver,
            performative=message.performative,
            content=json.dumps(message.content, default=str),
            created_at=message.timestamp
        )
        db.add(log_entry)
        db.commit()

    def send(self, message: AgentMessage, db: Optional[Session] = None) -> AgentMessage:
        """Point-to-point dispatch adhering strictly to FIPA message passing."""
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        try:
            # 1. Audit log incoming message
            self._persist_message(db, message)

            target_agent = self._agents.get(message.receiver)
            if not target_agent:
                # Receiver agent not found
                err_response = AgentMessage(
                    message_id=str(message.message_id) + "-err",
                    conversation_id=message.conversation_id,
                    sender="System",
                    receiver=message.sender,
                    performative=Performative.FAILURE,
                    content={"error": f"Agent '{message.receiver}' is not registered on the message bus."},
                    timestamp=message.timestamp
                )
                self._persist_message(db, err_response)
                return err_response

            # 2. Let target agent process message and reach decision
            reply = target_agent.process_message(message, db)
            if reply is not None:
                self._persist_message(db, reply)
                return reply
            else:
                ack_response = AgentMessage(
                    message_id=str(message.message_id) + "-ack",
                    conversation_id=message.conversation_id,
                    sender=message.receiver,
                    receiver=message.sender,
                    performative=Performative.INFORM,
                    content={"status": "acknowledged"},
                    timestamp=message.timestamp
                )
                self._persist_message(db, ack_response)
                return ack_response

        finally:
            if should_close_db:
                db.close()

    def broadcast(self, message: AgentMessage, db: Optional[Session] = None) -> List[AgentMessage]:
        """Broadcast an INFORM or alert message to all interested agents."""
        should_close_db = False
        if db is None:
            db = SessionLocal()
            should_close_db = True

        responses: List[AgentMessage] = []
        try:
            self._persist_message(db, message)
            for agent_name, agent in self._agents.items():
                if agent_name != message.sender:
                    # deliver broadcast copy
                    directed = AgentMessage(
                        message_id=f"{message.message_id}-{agent_name}",
                        conversation_id=message.conversation_id,
                        sender=message.sender,
                        receiver=agent_name,
                        performative=message.performative,
                        content=message.content,
                        timestamp=message.timestamp
                    )
                    resp = agent.process_message(directed, db)
                    if resp:
                        self._persist_message(db, resp)
                        responses.append(resp)
            return responses
        finally:
            if should_close_db:
                db.close()

agent_bus = AgentMessageBus()
