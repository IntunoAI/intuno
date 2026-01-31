"""Task domain model (orchestrator execution)."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Task(BaseModel):
    """
    Represents an orchestrator task: goal + input, status, result, and steps.
    Steps are stored as JSONB (list of {step_id, status, result?, error?}).
    """

    __tablename__: str = "tasks"

    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    integration_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("integrations.id"), nullable=True
    )
    status: Column[str] = Column(String(32), nullable=False, default="pending")
    goal: Column[str] = Column(Text, nullable=False)
    input: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    result: Column[Optional[Dict[str, Any]]] = Column(JSONB, nullable=True)
    error_message: Column[Optional[str]] = Column(Text, nullable=True)
    conversation_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("conversations.id"), nullable=True
    )
    message_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("messages.id"), nullable=True
    )
    external_user_id: Column[Optional[str]] = Column(String(255), nullable=True)
    idempotency_key: Column[Optional[str]] = Column(String(255), nullable=True, unique=True)
    steps: Column[Optional[List[Dict[str, Any]]]] = Column(JSONB, nullable=True)

    # Relationships
    user = relationship("User", back_populates="tasks")
    integration = relationship("Integration", back_populates="tasks")
    conversation = relationship("Conversation", back_populates="tasks")
    message = relationship("Message", back_populates="tasks")


__all__ = ["Task"]
