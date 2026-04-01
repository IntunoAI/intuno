"""Communication network domain models.

A CommunicationNetwork groups participants (agents, personas) that can
exchange messages through calls, messages, or mailboxes.
"""

import enum
from typing import Optional
from uuid import UUID

from sqlalchemy import Column, Enum, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
from sqlalchemy.orm import relationship

from src.models.base import BaseModel


class TopologyType(str, enum.Enum):
    mesh = "mesh"
    star = "star"
    ring = "ring"
    custom = "custom"


class NetworkStatus(str, enum.Enum):
    active = "active"
    paused = "paused"
    closed = "closed"


class ParticipantType(str, enum.Enum):
    agent = "agent"
    persona = "persona"
    orchestrator = "orchestrator"


class ParticipantStatus(str, enum.Enum):
    active = "active"
    disconnected = "disconnected"
    removed = "removed"


class ChannelType(str, enum.Enum):
    call = "call"
    message = "message"
    mailbox = "mailbox"


class MessageStatus(str, enum.Enum):
    pending = "pending"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class CommunicationNetwork(BaseModel):
    """A group of participants that share a communication context."""

    __tablename__: str = "communication_networks"

    owner_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("users.id"), nullable=False
    )
    name: Column[str] = Column(String(255), nullable=False)
    topology_type: Column[str] = Column(
        Enum(TopologyType), nullable=False, default=TopologyType.mesh
    )
    metadata_: Column[Optional[dict]] = Column("metadata", JSONB, nullable=True)
    status: Column[str] = Column(
        Enum(NetworkStatus), nullable=False, default=NetworkStatus.active
    )

    # Relationships
    owner = relationship("User")
    participants = relationship(
        "NetworkParticipant",
        back_populates="network",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "NetworkMessage",
        back_populates="network",
        cascade="all, delete-orphan",
        order_by="NetworkMessage.created_at",
    )


class NetworkParticipant(BaseModel):
    """An entity registered in a communication network."""

    __tablename__: str = "network_participants"

    network_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("communication_networks.id"), nullable=False
    )
    agent_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("agents.id"), nullable=True
    )
    participant_type: Column[str] = Column(
        Enum(ParticipantType), nullable=False, default=ParticipantType.agent
    )
    name: Column[str] = Column(String(255), nullable=False)
    callback_url: Column[Optional[str]] = Column(Text, nullable=True)
    polling_enabled: Column[bool] = Column(Boolean, nullable=False, default=False)
    capabilities: Column[Optional[dict]] = Column(JSONB, nullable=True)
    status: Column[str] = Column(
        Enum(ParticipantStatus), nullable=False, default=ParticipantStatus.active
    )

    # Relationships
    network = relationship("CommunicationNetwork", back_populates="participants")
    agent = relationship("Agent")
    sent_messages = relationship(
        "NetworkMessage",
        back_populates="sender",
        foreign_keys="NetworkMessage.sender_participant_id",
    )
    received_messages = relationship(
        "NetworkMessage",
        back_populates="recipient",
        foreign_keys="NetworkMessage.recipient_participant_id",
    )


class NetworkMessage(BaseModel):
    """A message exchanged within a communication network."""

    __tablename__: str = "network_messages"

    network_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("communication_networks.id"), nullable=False
    )
    sender_participant_id: Column[UUID] = Column(
        PostgresUUID, ForeignKey("network_participants.id"), nullable=False
    )
    recipient_participant_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("network_participants.id"), nullable=True
    )
    channel_type: Column[str] = Column(
        Enum(ChannelType), nullable=False
    )
    content: Column[str] = Column(Text, nullable=False)
    metadata_: Column[Optional[dict]] = Column("metadata", JSONB, nullable=True)
    status: Column[str] = Column(
        Enum(MessageStatus), nullable=False, default=MessageStatus.pending
    )
    in_reply_to_id: Column[Optional[UUID]] = Column(
        PostgresUUID, ForeignKey("network_messages.id"), nullable=True
    )

    # Relationships
    network = relationship("CommunicationNetwork", back_populates="messages")
    sender = relationship(
        "NetworkParticipant",
        back_populates="sent_messages",
        foreign_keys=[sender_participant_id],
    )
    recipient = relationship(
        "NetworkParticipant",
        back_populates="received_messages",
        foreign_keys=[recipient_participant_id],
    )
    in_reply_to = relationship("NetworkMessage", remote_side="NetworkMessage.id")
