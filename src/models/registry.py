"""Registry domain models."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class AgentRating(BaseModel):
    """User rating for an agent (optionally for a specific capability)."""

    __tablename__: str = "agent_ratings"

    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    agent_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=False
    )
    capability_id: Column[Optional[str]] = Column(String, nullable=True)
    score: Column[int] = Column(Integer, nullable=False)  # 1-5
    comment: Column[Optional[str]] = Column(Text, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="ratings")

    # Indexes: agent_id for aggregate/list by agent; user_id for "ratings by user"
    __table_args__ = (
        Index("idx_agent_ratings_agent_id", "agent_id"),
        Index("idx_agent_ratings_user_id", "user_id"),
        Index("idx_agent_ratings_agent_updated", "agent_id", "updated_at"),
    )

    # Uniqueness: one per (user_id, agent_id) when capability_id is NULL;
    # one per (user_id, agent_id, capability_id) when set. Enforced by partial
    # unique indexes in migration.


class Agent(BaseModel):
    """Represents an AI agent in the registry."""

    __tablename__: str = "agents"

    agent_id: Column[str] = Column(String, nullable=False, unique=True, index=True)
    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    brand_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("brands.id"), nullable=True, index=True
    )
    name: Column[str] = Column(String, nullable=False)
    description: Column[str] = Column(Text, nullable=False)
    version: Column[str] = Column(String, nullable=False)
    invoke_endpoint: Column[str] = Column(String, nullable=False)
    manifest_json: Column[Dict[str, Any]] = Column(JSONB, nullable=False)
    tags: Column[List[str]] = Column(ARRAY(String), nullable=False, default=list)
    category: Column[Optional[str]] = Column(String, nullable=True)
    trust_verification: Column[str] = Column(String, nullable=False)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)
    is_brand_agent: Column[bool] = Column(Boolean, default=False, nullable=False, server_default="false")
    qdrant_point_id: Column[UUID] = Column(PostgresUUID, nullable=True, index=True)
    embedding_version: Column[str] = Column(String, nullable=False, default="1.0", server_default="1.0")

    # Relationships
    user = relationship("User", back_populates="agents")
    brand = relationship(
        "Brand",
        back_populates="agents",
        foreign_keys=[brand_id],
    )
    capabilities = relationship("Capability", back_populates="agent", cascade="all, delete-orphan")
    requirements = relationship("AgentRequirement", back_populates="agent", cascade="all, delete-orphan")
    invocation_logs = relationship("InvocationLog", back_populates="target_agent")
    ratings = relationship("AgentRating", back_populates="agent", cascade="all, delete-orphan")
    credentials = relationship("AgentCredential", back_populates="agent", cascade="all, delete-orphan")

    # Indexes for performance
    __table_args__ = (
        Index("idx_agents_tags", "tags", postgresql_using="gin"),
        Index("idx_agents_category", "category"),
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


class AgentCredential(BaseModel):
    """Per-agent API key or bearer token for broker invoke auth."""

    __tablename__: str = "agent_credentials"

    agent_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=False
    )
    credential_type: Column[str] = Column(String, nullable=False)  # api_key | bearer_token
    encrypted_value: Column[str] = Column(Text, nullable=False)
    auth_header: Column[Optional[str]] = Column(String, nullable=True)  # e.g. X-API-Key, Authorization
    auth_scheme: Column[Optional[str]] = Column(String, nullable=True)  # e.g. Bearer (for Authorization header)

    # Relationships
    agent = relationship("Agent", back_populates="credentials")

    __table_args__ = (
        Index("idx_agent_credentials_agent_id", "agent_id"),
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
