"""Registry domain models."""

from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, Column, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Agent(BaseModel):
    """Represents an AI agent in the registry."""

    __tablename__: str = "agents"

    agent_id: Column[str] = Column(String, nullable=False, unique=True, index=True)
    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    name: Column[str] = Column(String, nullable=False)
    description: Column[str] = Column(Text, nullable=False)
    version: Column[str] = Column(String, nullable=False)
    invoke_endpoint: Column[str] = Column(String, nullable=False)
    manifest_json: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    tags: Column[List[str]] = Column(ARRAY(String), nullable=False, default=list)
    trust_verification: Column[str] = Column(String, nullable=False)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)
    qdrant_point_id: Column[UUID] = Column(PostgresUUID, nullable=True, index=True)
    embedding_version: Column[str] = Column(String, nullable=False, default="1.0", server_default="1.0")

    # Relationships
    user = relationship("User", back_populates="agents")
    capabilities = relationship("Capability", back_populates="agent", cascade="all, delete-orphan")
    requirements = relationship("AgentRequirement", back_populates="agent", cascade="all, delete-orphan")
    invocation_logs = relationship("InvocationLog", back_populates="target_agent")

    # Indexes for performance
    __table_args__ = (
        Index("idx_agents_tags", "tags", postgresql_using="gin"),
    )


class Capability(BaseModel):
    """Represents a capability of an agent."""

    __tablename__: str = "capabilities"

    agent_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=False
    )
    capability_id: Column[str] = Column(String, nullable=False)
    input_schema: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    output_schema: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    auth_type: Column[str] = Column(String, nullable=False)
    qdrant_point_id: Column[UUID] = Column(PostgresUUID, nullable=True, index=True)
    embedding_version: Column[str] = Column(String, nullable=False, default="1.0", server_default="1.0")

    # Relationships
    agent = relationship("Agent", back_populates="capabilities")

    # Indexes for performance
    __table_args__ = (
        Index("idx_capabilities_agent_capability", "agent_id", "capability_id"),
    )


class AgentRequirement(BaseModel):
    """Represents a capability requirement for an agent."""

    __tablename__: str = "agent_requirements"

    agent_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=False
    )
    required_capability: Column[str] = Column(String, nullable=False)

    # Relationships
    agent = relationship("Agent", back_populates="requirements")
