"""Brand domain models."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import relationship

from .base import BaseModel


class Brand(BaseModel):
    """Represents a brand/organization owned by a user."""

    __tablename__: str = "brands"

    owner_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    name: Column[str] = Column(String, nullable=False)
    slug: Column[str] = Column(String, nullable=False, unique=True, index=True)
    description: Column[Optional[str]] = Column(Text, nullable=True)
    website: Column[Optional[str]] = Column(String, nullable=True)
    logo_url: Column[Optional[str]] = Column(String, nullable=True)
    verification_email: Column[Optional[str]] = Column(String, nullable=True)
    brand_details: Column[Optional[str]] = Column(Text, nullable=True)  # Free-text: anything the brand agent should know
    verification_code: Column[Optional[str]] = Column(String, nullable=True)
    verification_code_expires_at: Column[Optional[datetime]] = Column(
        DateTime(timezone=True), nullable=True
    )
    verification_status: Column[str] = Column(
        String, nullable=False, default="pending", server_default="pending"
    )
    verified_at: Column[Optional[datetime]] = Column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    owner = relationship("User", back_populates="brands")
    agents = relationship(
        "Agent",
        back_populates="brand",
        foreign_keys="Agent.brand_id",
    )

    __table_args__ = (
        Index("idx_brands_owner_id", "owner_id"),
        Index("idx_brands_verification_status", "verification_status"),
    )
