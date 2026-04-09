"""add communication networks, participants, and messages tables

Revision ID: df05a2cb4da2
Revises: 2c185be2c005
Create Date: 2026-04-01 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "df05a2cb4da2"
down_revision = "2c185be2c005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Communication networks
    op.create_table(
        "communication_networks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("topology_type", sa.String(20), nullable=False, server_default="mesh"),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_communication_networks_owner_id", "communication_networks", ["owner_id"])

    # Network participants
    op.create_table(
        "network_participants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "network_id",
            UUID(as_uuid=True),
            sa.ForeignKey("communication_networks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("participant_type", sa.String(20), nullable=False, server_default="agent"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("callback_url", sa.Text, nullable=True),
        sa.Column("polling_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("capabilities", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_network_participants_network_id", "network_participants", ["network_id"])
    op.create_index("ix_network_participants_agent_id", "network_participants", ["agent_id"])

    # Network messages
    op.create_table(
        "network_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "network_id",
            UUID(as_uuid=True),
            sa.ForeignKey("communication_networks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sender_participant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("network_participants.id"),
            nullable=False,
        ),
        sa.Column(
            "recipient_participant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("network_participants.id"),
            nullable=True,
        ),
        sa.Column("channel_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "in_reply_to_id",
            UUID(as_uuid=True),
            sa.ForeignKey("network_messages.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_network_messages_network_id", "network_messages", ["network_id"])
    op.create_index(
        "ix_network_messages_sender", "network_messages", ["sender_participant_id"]
    )
    op.create_index(
        "ix_network_messages_recipient", "network_messages", ["recipient_participant_id"]
    )
    op.create_index(
        "ix_network_messages_created_at", "network_messages", ["network_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("network_messages")
    op.drop_table("network_participants")
    op.drop_table("communication_networks")
