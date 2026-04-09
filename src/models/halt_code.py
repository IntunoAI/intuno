"""Halt code model — distributed kill switch codes for trustees."""

from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from .base import BaseModel


class HaltCode(BaseModel):
    """A halt code held by a trustee who can stop the platform."""

    __tablename__: str = "halt_codes"

    code_hash: Column[str] = Column(String, nullable=False)
    label: Column[str] = Column(String, nullable=False)
    trustee_name: Column[str] = Column(String, nullable=False)
    trustee_email: Column[Optional[str]] = Column(String, nullable=True)
    is_master: Column[bool] = Column(Boolean, default=False, nullable=False)
    is_active: Column[bool] = Column(Boolean, default=True, nullable=False)
    created_by: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
