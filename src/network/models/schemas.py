"""Pydantic request/response schemas for communication networks."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Network schemas ──────────────────────────────────────────────────


class NetworkCreate(BaseModel):
    name: str = Field(..., max_length=255)
    topology_type: str = Field(default="mesh", description="mesh | star | ring | custom")
    metadata: Optional[dict[str, Any]] = None


class NetworkUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    topology_type: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class NetworkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    name: str
    topology_type: str
    metadata_: Optional[dict[str, Any]] = Field(default=None, alias="metadata_")
    status: str
    created_at: datetime
    updated_at: datetime


# ── Participant schemas ──────────────────────────────────────────────


class ParticipantJoin(BaseModel):
    agent_id: Optional[UUID] = None
    participant_type: str = Field(default="agent", description="agent | persona | orchestrator")
    name: str = Field(..., max_length=255)
    callback_url: Optional[str] = None
    polling_enabled: bool = False
    capabilities: Optional[dict[str, Any]] = None


class ParticipantUpdate(BaseModel):
    callback_url: Optional[str] = None
    polling_enabled: Optional[bool] = None
    capabilities: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class ParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    network_id: UUID
    agent_id: Optional[UUID] = None
    participant_type: str
    name: str
    callback_url: Optional[str] = None
    polling_enabled: bool
    capabilities: Optional[dict[str, Any]] = None
    status: str
    created_at: datetime
    updated_at: datetime


# ── Message schemas ──────────────────────────────────────────────────


class NetworkMessageCreate(BaseModel):
    recipient_participant_id: Optional[UUID] = None
    channel_type: str = Field(..., description="call | message | mailbox")
    content: str
    metadata: Optional[dict[str, Any]] = None
    in_reply_to_id: Optional[UUID] = None


class NetworkMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    network_id: UUID
    sender_participant_id: UUID
    recipient_participant_id: Optional[UUID] = None
    channel_type: str
    content: str
    metadata_: Optional[dict[str, Any]] = Field(default=None, alias="metadata_")
    status: str
    in_reply_to_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


# ── Context snapshot ─────────────────────────────────────────────────


class ContextEntry(BaseModel):
    sender: str
    recipient: Optional[str] = None
    channel: str
    content: str
    timestamp: datetime


class NetworkContextSnapshot(BaseModel):
    network_id: UUID
    participant_count: int
    message_count: int
    entries: list[ContextEntry]
