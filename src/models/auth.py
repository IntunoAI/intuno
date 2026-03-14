"""Auth domain models."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class User(BaseModel):
    """Represents a user in the system."""

    __tablename__: str = "users"

    email: Column[str] = Column(String, nullable=False, unique=True, index=True)
    password_hash: Column[str] = Column(String, nullable=False)
    first_name: Column[str] = Column(String, nullable=True)
    last_name: Column[str] = Column(String, nullable=True)
    phone_number: Column[str] = Column(String, nullable=True, unique=True)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)

    # Relationships
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="user", cascade="all, delete-orphan")
    brands = relationship("Brand", back_populates="owner", cascade="all, delete-orphan")
    integrations = relationship("Integration", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    invocation_logs = relationship("InvocationLog", foreign_keys="InvocationLog.caller_user_id", overlaps="caller_user")


class ApiKey(BaseModel):
    """Represents an API key for a user."""

    __tablename__: str = "api_keys"

    user_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    integration_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("integrations.id"), nullable=True
    )
    key_hash: Column[str] = Column(String, nullable=False)
    name: Column[str] = Column(String, nullable=False)
    last_used_at: Column[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)
    expires_at: Column[Optional[datetime]] = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="api_keys")
    integration = relationship("Integration", back_populates="api_keys", foreign_keys=[integration_id])
