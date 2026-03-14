"""Conversation domain schemas. Response schemas accept ORM via from_attributes."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ConversationCreate(BaseModel):
    """Conversation creation schema."""

    title: Optional[str] = None
    integration_id: Optional[UUID] = None


class ConversationUpdate(BaseModel):
    """Conversation update schema (PATCH semantics)."""

    title: Optional[str] = None
    integration_id: Optional[UUID] = None


class ConversationResponse(BaseModel):
    """Conversation response schema; parse from ORM with model_validate(conv)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    integration_id: Optional[UUID] = None
    title: Optional[str] = None
    external_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    """Conversation list item schema; same shape as ConversationResponse."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    integration_id: Optional[UUID] = None
    title: Optional[str] = None
    external_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
