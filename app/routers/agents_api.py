from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents import agent_bus
from app.database import get_db
from app.models import Notification, User
from app.schemas import AgentMessage, NotificationOut
from app.security import get_current_user

router = APIRouter(tags=["Multi-Agent HTTP Inboxes & Notifications"])

@router.get("/api/agents")
def list_agents_api():
    """Returns the roster of active agents on the message bus, their goals and performatives."""
    agents_info = []
    for name in agent_bus.list_agents():
        agent = agent_bus.get_agent(name)
        agents_info.append({
            "name": agent.name,
            "goal": agent.goal,
            "inbox_url": f"/api/agents/{agent.name}/inbox"
        })
    return {"registered_agents": agents_info}

@router.post("/api/agents/{agent_name}/inbox", response_model=AgentMessage)
def agent_http_inbox(
    agent_name: str,
    message: AgentMessage,
    db: Session = Depends(get_db)
):
    """
    Public HTTP inbox endpoint for each agent.
    Accepts standard FIPA-ACL JSON messages, dispatches through internal bus, and returns response.
    """
    target = agent_bus.get_agent(agent_name)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found on message bus."
        )

    # Ensure receiver matches target agent
    message.receiver = agent_name
    reply = agent_bus.send(message, db=db)
    return reply

@router.get("/api/notifications/my", response_model=List[NotificationOut])
def get_user_notifications(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.created_at.desc()).limit(20).all()

@router.post("/api/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == user.id
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found.")
    notif.is_read = True
    db.commit()
    return {"status": "marked_as_read", "id": notification_id}
