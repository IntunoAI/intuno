"""Callback routes: webhook receiver for external agents to push messages back.

This is the key endpoint that enables bidirectional communication.
When Intuno delivers a message to an external agent, the payload includes
a signed ``reply_url`` pointing to this endpoint.  The agent can POST back
to proactively send messages into the network.

The reply_url is HMAC-signed so only the intended recipient can use it.
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from src.exceptions import ForbiddenException
from src.network.models.schemas import (
    MAX_CONTENT_LENGTH,
    ChannelLiteral,
    NetworkMessageResponse,
)
from src.network.services.channels import ChannelService
from src.network.utils.callback_auth import verify_callback_signature

router = APIRouter(prefix="/networks", tags=["Callbacks"])


class CallbackPayload(BaseModel):
    """Payload an external agent sends to its reply_url."""

    content: str = Field(..., max_length=MAX_CONTENT_LENGTH)
    recipient_participant_id: Optional[UUID] = None
    channel_type: ChannelLiteral = Field(default="message")
    metadata: Optional[dict[str, Any]] = None
    in_reply_to_id: Optional[UUID] = None


@router.post(
    "/{network_id}/participants/{participant_id}/callback",
    response_model=NetworkMessageResponse,
)
async def receive_callback(
    network_id: UUID,
    participant_id: UUID,
    data: CallbackPayload,
    request: Request,
    sig: str = Query(..., description="HMAC signature from the signed reply_url"),
    exp: str = Query(..., description="Expiry timestamp from the signed reply_url"),
    service: ChannelService = Depends(),
) -> NetworkMessageResponse:
    """Receive a proactive message from an external agent.

    Authentication is via the HMAC-signed reply_url — the ``sig`` and
    ``exp`` query parameters are validated before processing.

    The external agent can:
    - Reply to a specific message (in_reply_to_id)
    - Target a specific recipient (recipient_participant_id)
    - Choose a channel type (call/message/mailbox)
    """
    if not verify_callback_signature(network_id, participant_id, sig, exp):
        raise ForbiddenException("Invalid or expired callback signature")

    service.set_http_client(request.app.state.http_client)
    return await service.handle_callback(
        network_id=network_id,
        participant_id=participant_id,
        content=data.content,
        recipient_participant_id=data.recipient_participant_id,
        channel_type=data.channel_type,
        metadata=data.metadata,
        in_reply_to_id=data.in_reply_to_id,
    )
