"""Repository for communication network domain operations."""

from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.network.models.entities import (
    CommunicationNetwork,
    NetworkMessage,
    NetworkParticipant,
    ParticipantStatus,
)


class NetworkRepository:
    """CRUD for communication networks, participants, and messages."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    # ── Networks ─────────────────────────────────────────────────────

    async def create_network(self, network: CommunicationNetwork) -> CommunicationNetwork:
        self.session.add(network)
        await self.session.commit()
        await self.session.refresh(network)
        return network

    async def get_network(self, network_id: UUID) -> Optional[CommunicationNetwork]:
        result = await self.session.execute(
            select(CommunicationNetwork)
            .where(CommunicationNetwork.id == network_id)
            .options(selectinload(CommunicationNetwork.participants))
        )
        return result.scalar_one_or_none()

    async def list_networks(
        self,
        owner_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CommunicationNetwork]:
        result = await self.session.execute(
            select(CommunicationNetwork)
            .where(CommunicationNetwork.owner_id == owner_id)
            .order_by(CommunicationNetwork.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update_network(self, network: CommunicationNetwork) -> CommunicationNetwork:
        await self.session.commit()
        await self.session.refresh(network)
        return network

    async def delete_network(self, network_id: UUID) -> bool:
        network = await self.get_network(network_id)
        if network:
            await self.session.delete(network)
            await self.session.commit()
            return True
        return False

    # ── Participants ─────────────────────────────────────────────────

    async def add_participant(self, participant: NetworkParticipant) -> NetworkParticipant:
        self.session.add(participant)
        await self.session.commit()
        await self.session.refresh(participant)
        return participant

    async def get_participant(self, participant_id: UUID) -> Optional[NetworkParticipant]:
        result = await self.session.execute(
            select(NetworkParticipant).where(NetworkParticipant.id == participant_id)
        )
        return result.scalar_one_or_none()

    async def get_participant_by_agent(
        self, network_id: UUID, agent_id: UUID
    ) -> Optional[NetworkParticipant]:
        result = await self.session.execute(
            select(NetworkParticipant).where(
                NetworkParticipant.network_id == network_id,
                NetworkParticipant.agent_id == agent_id,
                NetworkParticipant.status == ParticipantStatus.active,
            )
        )
        return result.scalar_one_or_none()

    async def list_participants(
        self,
        network_id: UUID,
        active_only: bool = True,
    ) -> list[NetworkParticipant]:
        q = select(NetworkParticipant).where(
            NetworkParticipant.network_id == network_id
        )
        if active_only:
            q = q.where(NetworkParticipant.status == ParticipantStatus.active)
        q = q.order_by(NetworkParticipant.created_at)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def update_participant(self, participant: NetworkParticipant) -> NetworkParticipant:
        await self.session.commit()
        await self.session.refresh(participant)
        return participant

    async def remove_participant(self, participant: NetworkParticipant) -> NetworkParticipant:
        participant.status = ParticipantStatus.removed
        await self.session.commit()
        await self.session.refresh(participant)
        return participant

    # ── Messages ─────────────────────────────────────────────────────

    async def create_message(self, message: NetworkMessage) -> NetworkMessage:
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def get_message(self, message_id: UUID) -> Optional[NetworkMessage]:
        result = await self.session.execute(
            select(NetworkMessage).where(NetworkMessage.id == message_id)
        )
        return result.scalar_one_or_none()

    async def list_messages(
        self,
        network_id: UUID,
        limit: int = 100,
        offset: int = 0,
        channel_type: Optional[str] = None,
        participant_id: Optional[UUID] = None,
    ) -> list[NetworkMessage]:
        q = (
            select(NetworkMessage)
            .where(NetworkMessage.network_id == network_id)
            .order_by(NetworkMessage.created_at)
        )
        if channel_type:
            q = q.where(NetworkMessage.channel_type == channel_type)
        if participant_id:
            q = q.where(
                (NetworkMessage.sender_participant_id == participant_id)
                | (NetworkMessage.recipient_participant_id == participant_id)
            )
        q = q.limit(limit).offset(offset)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def get_context(
        self,
        network_id: UUID,
        limit: int = 50,
    ) -> list[NetworkMessage]:
        """Get recent messages for building network context."""
        result = await self.session.execute(
            select(NetworkMessage)
            .where(NetworkMessage.network_id == network_id)
            .options(
                selectinload(NetworkMessage.sender),
                selectinload(NetworkMessage.recipient),
            )
            .order_by(NetworkMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(result.scalars().all())
        messages.reverse()  # chronological order
        return messages

    async def get_inbox(
        self,
        network_id: UUID,
        recipient_id: UUID,
        limit: int = 50,
    ) -> list[NetworkMessage]:
        """Get unread messages where participant is the recipient."""
        q = (
            select(NetworkMessage)
            .where(
                NetworkMessage.network_id == network_id,
                NetworkMessage.recipient_participant_id == recipient_id,
                NetworkMessage.status.in_(["pending", "delivered"]),
            )
            .order_by(NetworkMessage.created_at)
            .limit(limit)
        )
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def update_message(self, message: NetworkMessage) -> NetworkMessage:
        await self.session.commit()
        await self.session.refresh(message)
        return message
