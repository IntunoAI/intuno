"""Integration domain model."""

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Integration(BaseModel):
    """Represents an integration (e.g. chat UI, LangChain app) for a user."""

    __tablename__: str = "integrations"

    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    name: Column[str] = Column(String, nullable=False)
    kind: Column[Optional[str]] = Column(String, nullable=True)
    metadata_: Column[Optional[Dict[str, Any]]] = Column("metadata", JSONB, nullable=True)

    # Relationships
    user = relationship("User", back_populates="integrations")
    api_keys = relationship(
        "ApiKey",
        back_populates="integration",
        foreign_keys="ApiKey.integration_id",
        cascade="all, delete-orphan",
    )
    conversations = relationship("Conversation", back_populates="integration", cascade="all, delete-orphan")
    invocation_logs = relationship("InvocationLog", back_populates="integration")
    broker_config = relationship(
        "BrokerConfig",
        back_populates="integration",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tasks = relationship("Task", back_populates="integration", cascade="all, delete-orphan")
