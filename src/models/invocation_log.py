"""Invocation log model: records of agent invocations for auditing and metrics."""

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class InvocationLog(BaseModel):
    """Represents a log of an agent invocation."""

    __tablename__: str = "invocation_logs"

    caller_user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    target_agent_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=False
    )
    request_payload: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    response_payload: Column[Dict[str, Any]] = Column(JSONB, nullable=True)
    status_code: Column[int] = Column(Integer, nullable=False)
    latency_ms: Column[int] = Column(Integer, nullable=False)
    error_message: Column[Optional[str]] = Column(Text, nullable=True)
    integration_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("integrations.id"), nullable=True
    )
    conversation_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("conversations.id"), nullable=True
    )
    message_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("messages.id"), nullable=True
    )
    parent_invocation_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("invocation_logs.id"), nullable=True
    )

    # Relationships
    caller_user = relationship("User", foreign_keys=[caller_user_id], overlaps="invocation_logs")
    target_agent = relationship("Agent", back_populates="invocation_logs")
    integration = relationship("Integration", back_populates="invocation_logs")
    conversation = relationship("Conversation", back_populates="invocation_logs")
    message = relationship("Message", back_populates="invocation_logs")

    # Indexes: target_agent_id + created_at for quality/trending; caller_user_id for "my logs"
    __table_args__ = (
        Index("idx_invocation_logs_target_agent_id", "target_agent_id"),
        Index("idx_invocation_logs_target_agent_created_at", "target_agent_id", "created_at"),
        Index("idx_invocation_logs_caller_user_id", "caller_user_id"),
        Index("idx_invocation_logs_conversation_id", "conversation_id"),
    )
