"""Communication network service — business logic for networks and participants."""

from typing import Optional
from uuid import UUID

from fastapi import Depends

from src.exceptions import BadRequestException, NotFoundException
from src.network.models.entities import (
    ChannelType,
    CommunicationNetwork,
    NetworkMessage,
    NetworkParticipant,
    NetworkStatus,
    ParticipantStatus,
    ParticipantType,
    TopologyType,
)
from src.network.models.schemas import (
    NetworkCreate,
    NetworkMessageCreate,
    NetworkUpdate,
    ParticipantJoin,
    ParticipantUpdate,
)
from src.network.repositories.networks import NetworkRepository
from src.network.utils.context_manager import NetworkContextManager


class NetworkService:
    """Service for communication network operations."""

    def __init__(
        self,
        repo: NetworkRepository = Depends(),
        context_manager: NetworkContextManager = Depends(),
    ):
        self.repo = repo
        self.ctx = context_manager

    # ── Networks ─────────────────────────────────────────────────────

    async def create_network(
        self, owner_id: UUID, data: NetworkCreate
    ) -> CommunicationNetwork:
        network = CommunicationNetwork(
            owner_id=owner_id,
            name=data.name,
            topology_type=TopologyType(data.topology_type),
            metadata_=data.metadata,
            status=NetworkStatus.active,
        )
        return await self.repo.create_network(network)

    async def get_network(self, network_id: UUID, owner_id: UUID) -> CommunicationNetwork:
        network = await self.repo.get_network(network_id)
        if not network or network.owner_id != owner_id:
            raise NotFoundException("Network")
        return network

    async def list_networks(
        self, owner_id: UUID, limit: int = 50, offset: int = 0
    ) -> list[CommunicationNetwork]:
        return await self.repo.list_networks(owner_id, limit, offset)

    async def update_network(
        self, network_id: UUID, owner_id: UUID, data: NetworkUpdate
    ) -> CommunicationNetwork:
        network = await self.get_network(network_id, owner_id)
        if data.name is not None:
            network.name = data.name
        if data.topology_type is not None:
            network.topology_type = TopologyType(data.topology_type)
        if data.status is not None:
            network.status = NetworkStatus(data.status)
        if data.metadata is not None:
            network.metadata_ = data.metadata
        return await self.repo.update_network(network)

    async def delete_network(self, network_id: UUID, owner_id: UUID) -> bool:
        network = await self.repo.get_network(network_id)
        if not network or network.owner_id != owner_id:
            return False
        await self.ctx.clear(network_id)
        return await self.repo.delete_network(network_id)

    # ── Participants ─────────────────────────────────────────────────

    async def join_network(
        self, network_id: UUID, owner_id: UUID, data: ParticipantJoin
    ) -> NetworkParticipant:
        network = await self.get_network(network_id, owner_id)
        if network.status != NetworkStatus.active:
            raise BadRequestException("Network is not active")
        if not data.callback_url and not data.polling_enabled:
            raise BadRequestException(
                "Participant must have a callback_url or polling_enabled"
            )
        if data.callback_url:
            from src.network.utils.url_validator import validate_callback_url
            validate_callback_url(data.callback_url)
        if data.agent_id:
            existing = await self.repo.get_participant_by_agent(network_id, data.agent_id)
            if existing:
                raise BadRequestException("Agent already in network")
        participant = NetworkParticipant(
            network_id=network_id,
            agent_id=data.agent_id,
            participant_type=ParticipantType(data.participant_type),
            name=data.name,
            callback_url=data.callback_url,
            polling_enabled=data.polling_enabled,
            capabilities=data.capabilities,
            status=ParticipantStatus.active,
        )
        return await self.repo.add_participant(participant)

    async def list_participants(
        self, network_id: UUID, owner_id: UUID
    ) -> list[NetworkParticipant]:
        await self.get_network(network_id, owner_id)
        return await self.repo.list_participants(network_id)

    async def update_participant(
        self,
        network_id: UUID,
        participant_id: UUID,
        owner_id: UUID,
        data: ParticipantUpdate,
    ) -> NetworkParticipant:
        await self.get_network(network_id, owner_id)
        participant = await self.repo.get_participant(participant_id)
        if not participant or participant.network_id != network_id:
            raise NotFoundException("Participant")
        if data.callback_url is not None:
            participant.callback_url = data.callback_url
        if data.polling_enabled is not None:
            participant.polling_enabled = data.polling_enabled
        if data.capabilities is not None:
            participant.capabilities = data.capabilities
        if data.status is not None:
            participant.status = ParticipantStatus(data.status)
        return await self.repo.update_participant(participant)

    async def leave_network(
        self, network_id: UUID, participant_id: UUID, owner_id: UUID
    ) -> bool:
        await self.get_network(network_id, owner_id)
        participant = await self.repo.get_participant(participant_id)
        if not participant or participant.network_id != network_id:
            return False
        await self.repo.remove_participant(participant)
        return True

    # ── Context ──────────────────────────────────────────────────────

    async def get_context(
        self, network_id: UUID, owner_id: UUID, limit: int = 50
    ) -> list[dict]:
        await self.get_network(network_id, owner_id)
        return await self.ctx.get_context_window(network_id, limit)

    async def get_context_from_db(
        self, network_id: UUID, owner_id: UUID, limit: int = 50
    ) -> list[NetworkMessage]:
        """Authoritative context from Postgres (slower but complete)."""
        await self.get_network(network_id, owner_id)
        return await self.repo.get_context(network_id, limit)

    # ── Messages (internal recording) ────────────────────────────────

    async def record_message(
        self,
        network_id: UUID,
        sender_participant_id: UUID,
        data: NetworkMessageCreate,
    ) -> NetworkMessage:
        """Record a message and update the Redis context cache."""
        sender = await self.repo.get_participant(sender_participant_id)
        if not sender or sender.network_id != network_id:
            raise BadRequestException("Sender is not a participant in this network")

        message = NetworkMessage(
            network_id=network_id,
            sender_participant_id=sender_participant_id,
            recipient_participant_id=data.recipient_participant_id,
            channel_type=ChannelType(data.channel_type),
            content=data.content,
            metadata_=data.metadata,
            in_reply_to_id=data.in_reply_to_id,
        )
        message = await self.repo.create_message(message)

        # Update Redis context cache
        recipient = None
        if data.recipient_participant_id:
            r = await self.repo.get_participant(data.recipient_participant_id)
            recipient = r.name if r else None

        await self.ctx.append(
            network_id,
            sender=sender.name,
            recipient=recipient,
            channel=data.channel_type,
            content=data.content,
            message_id=message.id,
        )
        return message

    async def list_messages(
        self,
        network_id: UUID,
        owner_id: UUID,
        limit: int = 100,
        offset: int = 0,
        channel_type: Optional[str] = None,
        participant_id: Optional[UUID] = None,
    ) -> list[NetworkMessage]:
        await self.get_network(network_id, owner_id)
        return await self.repo.list_messages(
            network_id, limit, offset, channel_type, participant_id
        )
