"""Channel service — calls, messages, and mailboxes.

Implements the three communication primitives with different timing
semantics.  Each interaction is recorded in the network context and
delivered to the recipient via the appropriate mechanism.
"""

import json
import logging
from typing import Any, Optional
from uuid import UUID

import httpx
from fastapi import Depends

from src.core.settings import settings
from src.exceptions import BadRequestException, ForbiddenException, NotFoundException
from src.network.models.entities import (
    ChannelType,
    CommunicationNetwork,
    MessageStatus,
    NetworkMessage,
    NetworkParticipant,
    NetworkStatus,
    ParticipantStatus,
)
from src.network.models.schemas import NetworkMessageCreate
from src.network.repositories.networks import NetworkRepository
from src.network.utils.callback_auth import sign_callback_url
from src.network.utils.context_manager import NetworkContextManager
from src.network.utils.topology import TopologyValidator

logger = logging.getLogger(__name__)


class ChannelService:
    """Unified service for calls, messages, and mailboxes."""

    def __init__(
        self,
        repo: NetworkRepository = Depends(),
        context_manager: NetworkContextManager = Depends(),
    ):
        self.repo = repo
        self.ctx = context_manager
        self._http_client: Optional[httpx.AsyncClient] = None
        self._topology = TopologyValidator()

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        self._http_client = client

    # ── Calls (synchronous, blocking) ────────────────────────────────

    async def call(
        self,
        network_id: UUID,
        sender_participant_id: UUID,
        recipient_participant_id: UUID,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        owner_id: Optional[UUID] = None,
    ) -> dict[str, Any]:
        """Synchronous call: send payload to recipient, wait for response.

        Returns a dict with the call result including the recipient's response.
        """
        sender, recipient, network = await self._validate_communication(
            network_id, sender_participant_id, recipient_participant_id,
            owner_id=owner_id,
        )

        if not recipient.callback_url:
            raise BadRequestException(
                "Recipient has no callback_url; cannot make a synchronous call"
            )

        # Record outgoing message
        outgoing = await self._record_message(
            network_id=network_id,
            sender=sender,
            recipient=recipient,
            channel_type=ChannelType.call,
            content=content,
            metadata=metadata,
        )

        # Build context window for the call
        context_entries = await self.ctx.get_context_window(network_id, limit=30)
        participants = await self.repo.list_participants(network_id)

        # Build the payload with signed reply_url
        payload = self._build_delivery_payload(
            network_id=network_id,
            sender=sender,
            recipient=recipient,
            channel="call",
            content=content,
            context=context_entries,
            participants=participants,
            message_id=outgoing.id,
        )

        # Synchronous HTTP call
        response_data = await self._deliver_http(
            recipient.callback_url,
            payload,
            timeout=settings.NETWORK_CALLBACK_TIMEOUT_SECONDS,
        )

        # Record the response as a message from recipient back to sender
        response_content = (
            json.dumps(response_data) if isinstance(response_data, dict) else str(response_data)
        )
        await self._record_message(
            network_id=network_id,
            sender=recipient,
            recipient=sender,
            channel_type=ChannelType.call,
            content=response_content,
            metadata={"in_reply_to": str(outgoing.id)},
        )

        # Mark outgoing as delivered
        outgoing.status = MessageStatus.delivered
        await self.repo.update_message(outgoing)

        return {
            "success": True,
            "message_id": str(outgoing.id),
            "response": response_data,
        }

    # ── Messages (near-real-time, non-blocking) ──────────────────────

    async def send_message(
        self,
        network_id: UUID,
        sender_participant_id: UUID,
        recipient_participant_id: UUID,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        owner_id: Optional[UUID] = None,
    ) -> NetworkMessage:
        """Non-blocking message: record and push via webhook.

        The sender does not block on the recipient's processing.  Delivery
        is best-effort with retries handled by the delivery worker.
        """
        sender, recipient, network = await self._validate_communication(
            network_id, sender_participant_id, recipient_participant_id,
            owner_id=owner_id,
        )

        # Record message and attempt delivery in one logical operation
        message = await self._record_message(
            network_id=network_id,
            sender=sender,
            recipient=recipient,
            channel_type=ChannelType.message,
            content=content,
            metadata=metadata,
        )

        # Attempt immediate webhook delivery (fire-and-forget style)
        if recipient.callback_url:
            context_entries = await self.ctx.get_context_window(network_id, limit=20)
            participants = await self.repo.list_participants(network_id)
            payload = self._build_delivery_payload(
                network_id=network_id,
                sender=sender,
                recipient=recipient,
                channel="message",
                content=content,
                context=context_entries,
                participants=participants,
                message_id=message.id,
            )
            try:
                await self._deliver_http(
                    recipient.callback_url,
                    payload,
                    timeout=settings.NETWORK_CALLBACK_TIMEOUT_SECONDS,
                )
                message.status = MessageStatus.delivered
            except Exception:
                logger.warning(
                    "Message delivery failed for participant %s; enqueuing for retry",
                    recipient_participant_id,
                )
                message.status = MessageStatus.pending
                # Enqueue for retry via delivery worker
                await self._enqueue_delivery(
                    recipient.callback_url, payload, str(message.id)
                )
            await self.repo.update_message(message)

        return message

    # ── Mailbox (fully asynchronous) ─────────────────────────────────

    async def send_to_mailbox(
        self,
        network_id: UUID,
        sender_participant_id: UUID,
        recipient_participant_id: UUID,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        owner_id: Optional[UUID] = None,
    ) -> NetworkMessage:
        """Async mailbox: store message, no push delivery."""
        sender, recipient, network = await self._validate_communication(
            network_id, sender_participant_id, recipient_participant_id,
            owner_id=owner_id,
        )

        return await self._record_message(
            network_id=network_id,
            sender=sender,
            recipient=recipient,
            channel_type=ChannelType.mailbox,
            content=content,
            metadata=metadata,
        )

    # ── Inbox (polling) ──────────────────────────────────────────────

    async def get_inbox(
        self,
        network_id: UUID,
        participant_id: UUID,
        channel_types: Optional[list[str]] = None,
        limit: int = 50,
        owner_id: Optional[UUID] = None,
    ) -> list[NetworkMessage]:
        """Get unread messages for a participant (recipient only)."""
        # Verify ownership
        if owner_id:
            network = await self.repo.get_network(network_id)
            if not network or network.owner_id != owner_id:
                raise ForbiddenException("You don't own this network")

        messages = await self.repo.get_inbox(
            network_id=network_id,
            recipient_id=participant_id,
            limit=limit,
        )
        if channel_types:
            messages = [m for m in messages if m.channel_type in channel_types]
        return messages

    async def acknowledge(
        self, network_id: UUID, message_ids: list[UUID],
        owner_id: Optional[UUID] = None,
    ) -> int:
        """Mark messages as read."""
        # Verify ownership
        if owner_id:
            network = await self.repo.get_network(network_id)
            if not network or network.owner_id != owner_id:
                raise ForbiddenException("You don't own this network")

        count = 0
        for msg_id in message_ids:
            message = await self.repo.get_message(msg_id)
            if message and message.network_id == network_id:
                message.status = MessageStatus.read
                await self.repo.update_message(message)
                count += 1
        return count

    # ── Callback (external agents pushing back) ──────────────────────

    async def handle_callback(
        self,
        network_id: UUID,
        participant_id: UUID,
        content: str,
        recipient_participant_id: Optional[UUID] = None,
        channel_type: str = "message",
        metadata: Optional[dict[str, Any]] = None,
        in_reply_to_id: Optional[UUID] = None,
    ) -> NetworkMessage:
        """Handle a proactive message from an external agent via callback URL.

        This is the key to bidirectionality: external agents POST to their
        signed reply_url and this method records the message in the network.
        """
        # Safety check: reject if platform is in emergency halt
        from src.services.safety import check_platform_halt
        await check_platform_halt()

        sender = await self.repo.get_participant(participant_id)
        if not sender or sender.network_id != network_id:
            raise NotFoundException("Participant")
        if sender.status != ParticipantStatus.active:
            raise BadRequestException("Participant is not active")

        network = await self.repo.get_network(network_id)
        if not network or network.status != NetworkStatus.active:
            raise BadRequestException("Network is not active")

        recipient = None
        if recipient_participant_id:
            recipient = await self.repo.get_participant(recipient_participant_id)
            if not recipient or recipient.network_id != network_id:
                raise NotFoundException("Recipient participant")

        message = await self._record_message(
            network_id=network_id,
            sender=sender,
            recipient=recipient,
            channel_type=ChannelType(channel_type),
            content=content,
            metadata=metadata,
            in_reply_to_id=in_reply_to_id,
        )

        # If there's a specific recipient with a callback_url, forward the message
        if recipient and recipient.callback_url and channel_type == "message":
            await self._forward_to_participant(
                network_id, sender, recipient, channel_type, content, message.id
            )
            message.status = MessageStatus.delivered
            await self.repo.update_message(message)

        return message

    # ── Internal helpers ─────────────────────────────────────────────

    async def _validate_communication(
        self,
        network_id: UUID,
        sender_id: UUID,
        recipient_id: UUID,
        owner_id: Optional[UUID] = None,
    ) -> tuple[NetworkParticipant, NetworkParticipant, CommunicationNetwork]:
        # Safety check: reject if platform is in emergency halt
        from src.services.safety import check_agent_active, check_platform_halt
        await check_platform_halt()

        network = await self.repo.get_network(network_id)
        if not network:
            raise NotFoundException("Network")
        if network.status != NetworkStatus.active:
            raise BadRequestException("Network is not active")

        # Ownership check: verify the calling user owns this network
        if owner_id and network.owner_id != owner_id:
            raise ForbiddenException("You don't own this network")

        sender = await self.repo.get_participant(sender_id)
        if not sender or sender.network_id != network_id:
            raise NotFoundException("Sender participant")
        if sender.status != ParticipantStatus.active:
            raise BadRequestException("Sender is not active")

        recipient = await self.repo.get_participant(recipient_id)
        if not recipient or recipient.network_id != network_id:
            raise NotFoundException("Recipient participant")
        if recipient.status != ParticipantStatus.active:
            raise BadRequestException("Recipient is not active")

        # Safety check: verify linked agents are still active
        if sender.agent_id:
            await check_agent_active(sender.agent_id)
        if recipient.agent_id:
            await check_agent_active(recipient.agent_id)

        # Topology validation: enforce communication constraints
        participants = await self.repo.list_participants(network_id)
        self._topology.validate(network, sender, recipient, participants)

        return sender, recipient, network

    async def _record_message(
        self,
        *,
        network_id: UUID,
        sender: NetworkParticipant,
        recipient: Optional[NetworkParticipant],
        channel_type: ChannelType,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
        in_reply_to_id: Optional[UUID] = None,
    ) -> NetworkMessage:
        message = NetworkMessage(
            network_id=network_id,
            sender_participant_id=sender.id,
            recipient_participant_id=recipient.id if recipient else None,
            channel_type=channel_type,
            content=content,
            metadata_=metadata,
            in_reply_to_id=in_reply_to_id,
        )
        message = await self.repo.create_message(message)

        await self.ctx.append(
            network_id,
            sender=sender.name,
            recipient=recipient.name if recipient else None,
            channel=channel_type.value,
            content=content,
            message_id=message.id,
        )
        return message

    def _build_delivery_payload(
        self,
        *,
        network_id: UUID,
        sender: NetworkParticipant,
        recipient: NetworkParticipant,
        channel: str,
        content: str,
        context: list[dict],
        participants: list[NetworkParticipant],
        message_id: UUID,
    ) -> dict[str, Any]:
        """Build the standard payload delivered to external agents."""
        # Build the signed reply_url
        raw_reply_url = (
            f"{settings.BASE_URL}/networks/{network_id}"
            f"/participants/{recipient.id}/callback"
        )
        signed_reply_url = sign_callback_url(
            raw_reply_url, network_id, recipient.id
        )

        return {
            "network_id": str(network_id),
            "message_id": str(message_id),
            "channel": channel,
            "sender": {
                "participant_id": str(sender.id),
                "name": sender.name,
            },
            "content": content,
            "context": context,
            "reply_url": signed_reply_url,
            "network_participants": [
                {"participant_id": str(p.id), "name": p.name}
                for p in participants
                if p.status == ParticipantStatus.active
            ],
        }

    async def _forward_to_participant(
        self,
        network_id: UUID,
        sender: NetworkParticipant,
        recipient: NetworkParticipant,
        channel_type: str,
        content: str,
        message_id: UUID,
    ) -> None:
        """Forward a message to a participant with a callback_url."""
        context_entries = await self.ctx.get_context_window(network_id, limit=20)
        participants = await self.repo.list_participants(network_id)
        payload = self._build_delivery_payload(
            network_id=network_id,
            sender=sender,
            recipient=recipient,
            channel=channel_type,
            content=content,
            context=context_entries,
            participants=participants,
            message_id=message_id,
        )
        try:
            await self._deliver_http(
                recipient.callback_url,
                payload,
                timeout=settings.NETWORK_CALLBACK_TIMEOUT_SECONDS,
            )
        except Exception:
            logger.warning(
                "Forwarding callback message failed for participant %s",
                recipient.id,
            )

    async def _enqueue_delivery(
        self, callback_url: str, payload: dict, message_id: str
    ) -> None:
        """Enqueue a failed delivery for retry via the delivery worker."""
        try:
            from src.network.utils.delivery_worker import DeliveryWorker
            redis = self.ctx._redis
            await DeliveryWorker.enqueue(
                redis,
                callback_url=callback_url,
                payload=payload,
                message_id=message_id,
            )
        except Exception:
            logger.warning(
                "Failed to enqueue delivery for retry (message %s)", message_id
            )

    async def _deliver_http(
        self,
        url: str,
        payload: dict[str, Any],
        timeout: int = 30,
    ) -> dict[str, Any]:
        """POST payload to an external agent's callback URL."""
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=timeout)

        try:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Intuno-Network/1.0",
                },
                timeout=timeout,
            )
            if response.status_code == 200:
                try:
                    return response.json()
                except Exception:
                    return {"raw_response": response.text}
            else:
                raise httpx.HTTPStatusError(
                    f"Callback returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
        finally:
            if owns_client:
                await client.aclose()
