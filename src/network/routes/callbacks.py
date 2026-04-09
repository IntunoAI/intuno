"""Callback routes: webhook receiver for external agents to push messages back.

This is the key endpoint that enables bidirectional communication.
When Intuno delivers a message to an external agent, the payload includes
a ``reply_url`` pointing to this endpoint.  The agent can POST back to
proactively send messages into the network.
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from src.network.models.schemas import NetworkMessageResponse
from src.network.services.channels import ChannelService

router = APIRouter(prefix="/networks", tags=["Callbacks"])


class CallbackPayload(BaseModel):
    """Payload an external agent sends to its reply_url."""

    content: str
    recipient_participant_id: Optional[UUID] = None
    channel_type: str = Field(default="message", description="message | call | mailbox")
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
    service: ChannelService = Depends(),
) -> NetworkMessageResponse:
    """Receive a proactive message from an external agent.

    No authentication required — the reply_url itself acts as a capability
    token.  The participant_id in the URL identifies the sender.

    The external agent can:
    - Reply to a specific message (in_reply_to_id)
    - Target a specific recipient (recipient_participant_id)
    - Broadcast to the network (omit recipient_participant_id)
    - Choose a channel type (call/message/mailbox)
    """
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
