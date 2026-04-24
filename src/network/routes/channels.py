"""Channel routes: calls, messages, mailboxes, inbox, and acknowledgment."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel

from src.core.auth import get_current_user_or_service as get_current_user
from src.models.auth import User
from src.network.models.schemas import (
    AckResponse,
    CallResponse,
    ChannelLiteral,
    ChannelRequest,
    NetworkMessageResponse,
)
from src.network.services.channels import ChannelService

router = APIRouter(prefix="/networks", tags=["Channels"])


class AckRequest(BaseModel):
    message_ids: list[UUID]


# ── Call ─────────────────────────────────────────────────────────────


@router.post("/{network_id}/call", response_model=CallResponse)
async def make_call(
    network_id: UUID,
    data: ChannelRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(),
) -> CallResponse:
    """Synchronous call to another participant. Blocks until response."""
    service.set_http_client(request.app.state.http_client)
    return await service.call(
        network_id=network_id,
        sender_participant_id=data.sender_participant_id,
        recipient_participant_id=data.recipient_participant_id,
        content=data.content,
        metadata=data.metadata,
        owner_id=current_user.id,
    )


# ── Message ──────────────────────────────────────────────────────────


@router.post(
    "/{network_id}/messages/send",
    response_model=NetworkMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    network_id: UUID,
    data: ChannelRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(),
) -> NetworkMessageResponse:
    """Send a near-real-time message. Non-blocking."""
    service.set_http_client(request.app.state.http_client)
    return await service.send_message(
        network_id=network_id,
        sender_participant_id=data.sender_participant_id,
        recipient_participant_id=data.recipient_participant_id,
        content=data.content,
        metadata=data.metadata,
        owner_id=current_user.id,
    )


# ── Mailbox ──────────────────────────────────────────────────────────


@router.post(
    "/{network_id}/mailbox",
    response_model=NetworkMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_to_mailbox(
    network_id: UUID,
    data: ChannelRequest,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(),
) -> NetworkMessageResponse:
    """Send to mailbox. Fully async — no push delivery."""
    return await service.send_to_mailbox(
        network_id=network_id,
        sender_participant_id=data.sender_participant_id,
        recipient_participant_id=data.recipient_participant_id,
        content=data.content,
        metadata=data.metadata,
        owner_id=current_user.id,
    )


# ── Inbox ────────────────────────────────────────────────────────────


@router.get("/{network_id}/inbox/{participant_id}")
async def get_inbox(
    network_id: UUID,
    participant_id: UUID,
    current_user: User = Depends(get_current_user),
    channel_type: Optional[ChannelLiteral] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    service: ChannelService = Depends(),
) -> List[NetworkMessageResponse]:
    """Poll inbox for a participant. Returns unread messages only."""
    channel_types = [channel_type] if channel_type else None
    messages = await service.get_inbox(
        network_id=network_id,
        participant_id=participant_id,
        channel_types=channel_types,
        limit=limit,
        owner_id=current_user.id,
    )
    return messages


# ── Acknowledge ──────────────────────────────────────────────────────


@router.post("/{network_id}/messages/ack", response_model=AckResponse)
async def acknowledge_messages(
    network_id: UUID,
    data: AckRequest,
    current_user: User = Depends(get_current_user),
    service: ChannelService = Depends(),
) -> AckResponse:
    """Mark messages as read."""
    count = await service.acknowledge(
        network_id, data.message_ids, owner_id=current_user.id
    )
    return AckResponse(acknowledged=count)
