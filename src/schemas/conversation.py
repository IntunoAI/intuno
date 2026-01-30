"""Conversation domain schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    """Conversation creation schema."""

    title: Optional[str] = None
    integration_id: Optional[UUID] = None


class ConversationUpdate(BaseModel):
    """Conversation update schema (PATCH semantics)."""

    title: Optional[str] = None
    integration_id: Optional[UUID] = None


class ConversationResponse(BaseModel):
    """Conversation response schema."""

    id: UUID
    user_id: UUID
    integration_id: Optional[UUID] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Conversation list item schema."""

    id: UUID
    user_id: UUID
    integration_id: Optional[UUID] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
