from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional
import json
import uuid

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import AgentBelief, MessageLog
from app.schemas import AgentMessage

class Performative:
    REQUEST = "REQUEST"
    AGREE = "AGREE"
    REFUSE = "REFUSE"
    PROPOSE = "PROPOSE"
    INFORM = "INFORM"
    FAILURE = "FAILURE"

class BaseAgent(ABC):
    def __init__(self, name: str, goal: str):
        self.name = name
        self.goal = goal
        self.bus = None  # Injected by AgentMessageBus

    def set_bus(self, bus):
        self.bus = bus

    def log_message(self, db: Session, message: AgentMessage):
        """Persist structured agent message to the audit log."""
        log_entry = MessageLog(
            message_id=message.message_id,
            conversation_id=message.conversation_id,
            sender=message.sender,
            receiver=message.receiver,
            performative=message.performative,
            content=json.dumps(message.content, default=str),
            created_at=datetime.utcnow()
        )
        db.add(log_entry)
        db.commit()

    # --- Persistent Beliefs System (Survives Restart) ---
    def get_belief(self, db: Session, key: str, default: Any = None) -> Any:
        record = db.query(AgentBelief).filter(
            AgentBelief.agent_name == self.name,
            AgentBelief.belief_key == key
        ).first()
        if record:
            try:
                return json.loads(record.belief_value)
            except Exception:
                return record.belief_value
        return default

    def set_belief(self, db: Session, key: str, value: Any):
        record = db.query(AgentBelief).filter(
            AgentBelief.agent_name == self.name,
            AgentBelief.belief_key == key
        ).first()
        value_str = json.dumps(value, default=str)
        if record:
            record.belief_value = value_str
            record.updated_at = datetime.utcnow()
        else:
            record = AgentBelief(
                agent_name=self.name,
                belief_key=key,
                belief_value=value_str,
                updated_at=datetime.utcnow()
            )
            db.add(record)
        db.commit()

    def build_message(
        self,
        receiver: str,
        performative: str,
        content: Dict[str, Any],
        conversation_id: Optional[str] = None
    ) -> AgentMessage:
        return AgentMessage(
            message_id=str(uuid.uuid4()),
            conversation_id=conversation_id or str(uuid.uuid4()),
            sender=self.name,
            receiver=receiver,
            performative=performative,
            content=content,
            timestamp=datetime.utcnow()
        )

    @abstractmethod
    def process_message(self, message: AgentMessage, db: Session) -> Optional[AgentMessage]:
        """Core decision cycle of the agent."""
        pass
