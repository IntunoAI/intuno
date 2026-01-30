"""Conversation domain model."""

from typing import Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Conversation(BaseModel):
    """Represents a conversation (e.g. chat thread) for a user."""

    __tablename__: str = "conversations"

    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    integration_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("integrations.id"), nullable=True
    )
    title: Column[Optional[str]] = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="conversations")
    integration = relationship("Integration", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    invocation_logs = relationship("InvocationLog", back_populates="conversation")
    tasks = relationship("Task", back_populates="conversation", cascade="all, delete-orphan")
