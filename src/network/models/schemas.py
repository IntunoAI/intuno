"""Pydantic request/response schemas for communication networks."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Shared type aliases ─────────────────────────────────────────────

TopologyLiteral = Literal["mesh", "star", "ring", "custom"]
ChannelLiteral = Literal["call", "message", "mailbox"]
NetworkStatusLiteral = Literal["active", "paused", "closed"]
ParticipantTypeLiteral = Literal["agent", "persona", "orchestrator"]
ParticipantStatusLiteral = Literal["active", "disconnected", "removed"]
MessageStatusLiteral = Literal["pending", "delivered", "read", "failed"]

# Maximum content size for messages (64 KB)
MAX_CONTENT_LENGTH = 65536


# ── Network schemas ──────────────────────────────────────────────────


class NetworkCreate(BaseModel):
    name: str = Field(..., max_length=255)
    topology_type: TopologyLiteral = Field(default="mesh")
    metadata: Optional[dict[str, Any]] = None


class NetworkUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    topology_type: Optional[TopologyLiteral] = None
    status: Optional[NetworkStatusLiteral] = None
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
    participant_type: ParticipantTypeLiteral = Field(default="agent")
    name: str = Field(..., max_length=255)
    callback_url: Optional[str] = None
    polling_enabled: bool = False
    capabilities: Optional[dict[str, Any]] = None


class ParticipantUpdate(BaseModel):
    callback_url: Optional[str] = None
    polling_enabled: Optional[bool] = None
    capabilities: Optional[dict[str, Any]] = None
    status: Optional[ParticipantStatusLiteral] = None


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
    channel_type: ChannelLiteral = Field(...)
    content: str = Field(..., max_length=MAX_CONTENT_LENGTH)
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


# ── Channel request/response (shared by call, message, mailbox) ─────


class ChannelRequest(BaseModel):
    """Shared request schema for all channel operations."""
    sender_participant_id: UUID
    recipient_participant_id: UUID
    content: str = Field(..., max_length=MAX_CONTENT_LENGTH)
    metadata: Optional[dict[str, Any]] = None


class CallResponse(BaseModel):
    """Response from a synchronous call."""
    success: bool
    message_id: str
    response: Any


class AckResponse(BaseModel):
    """Response from message acknowledgment."""
    acknowledged: int


# ── Context snapshot ─────────────────────────────────────────────────


class ContextEntry(BaseModel):
    sender: str
    recipient: Optional[str] = None
    channel: str
    content: str
    message_id: Optional[str] = None
    timestamp: datetime


class NetworkContextSnapshot(BaseModel):
    network_id: UUID
    participant_count: int
    message_count: int
    entries: list[ContextEntry]
