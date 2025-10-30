"""Broker domain models."""

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class InvocationLog(BaseModel):
    """Represents a log of an agent invocation."""

    __tablename__: str = "invocation_logs"

    caller_user_id: Column[UUID] = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    target_agent_id: Column[UUID] = Column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    capability_id: Column[str] = Column(String, nullable=False)
    request_payload: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    response_payload: Column[Dict[str, Any]] = Column(JSONB, nullable=True)
    status_code: Column[int] = Column(Integer, nullable=False)
    latency_ms: Column[int] = Column(Integer, nullable=False)
    error_message: Column[Optional[str]] = Column(Text, nullable=True)

    # Relationships
    caller_user = relationship("User", foreign_keys=[caller_user_id])
    target_agent = relationship("Agent", back_populates="invocation_logs")
