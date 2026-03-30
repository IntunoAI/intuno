"""Registry domain models."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, Boolean, Column, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class AgentRating(BaseModel):
    """User rating for an agent."""

    __tablename__: str = "agent_ratings"

    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    agent_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=False
    )
    score: Column[int] = Column(Integer, nullable=False)  # 1-5
    comment: Column[Optional[str]] = Column(Text, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="ratings")

    __table_args__ = (
        Index("idx_agent_ratings_agent_id", "agent_id"),
        Index("idx_agent_ratings_user_id", "user_id"),
        Index("idx_agent_ratings_agent_updated", "agent_id", "updated_at"),
    )


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
    version: Column[str] = Column(String, nullable=False, default="1.0.0", server_default="1.0.0")
    invoke_endpoint: Column[str] = Column(String, nullable=False)
    auth_type: Column[str] = Column(String, nullable=False, default="public", server_default="public")
    input_schema: Column[Optional[Dict[str, Any]]] = Column(JSONB, nullable=True)
    tags: Column[List[str]] = Column(ARRAY(String), nullable=False, default=list)
    category: Column[Optional[str]] = Column(String, nullable=True)
    trust_verification: Column[str] = Column(String, nullable=False, default="self-signed", server_default="self-signed")
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)
    is_brand_agent: Column[bool] = Column(Boolean, default=False, nullable=False, server_default="false")
    qdrant_point_id: Column[UUID] = Column(PostgresUUID, nullable=True, index=True)
    embedding_version: Column[str] = Column(String, nullable=False, default="1.0", server_default="1.0")

    # Economy: pricing fields
    pricing_strategy: Column[Optional[str]] = Column(
        String, nullable=True, default=None,
    )  # "fixed" | "dynamic" | "auction" | None (free)
    base_price: Column[Optional[float]] = Column(
        Float, nullable=True, default=None,
    )  # Credits per invocation (None = free)
    pricing_enabled: Column[bool] = Column(
        Boolean, nullable=False, default=False, server_default="false",
    )  # Opt-in to credit billing

    # Relationships
    user = relationship("User", back_populates="agents")
    brand = relationship(
        "Brand",
        back_populates="agents",
        foreign_keys=[brand_id],
    )
    invocation_logs = relationship("InvocationLog", back_populates="target_agent")
    ratings = relationship("AgentRating", back_populates="agent", cascade="all, delete-orphan")
    credentials = relationship("AgentCredential", back_populates="agent", cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="agent", uselist=False, lazy="selectin")

    # Indexes for performance
    __table_args__ = (
        Index("idx_agents_tags", "tags", postgresql_using="gin"),
        Index("idx_agents_category", "category"),
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
