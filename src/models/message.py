"""Message domain model."""

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Message(BaseModel):
    """Represents a message in a conversation (user, assistant, system, or tool)."""

    __tablename__: str = "messages"

    conversation_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("conversations.id"), nullable=False
    )
    role: Column[str] = Column(String(32), nullable=False)  # user | assistant | system | tool
    content: Column[str] = Column(Text, nullable=False)
    metadata_: Column[Optional[Dict[str, Any]]] = Column("metadata", JSONB, nullable=True)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    invocation_logs = relationship("InvocationLog", back_populates="message")
