"""add halt_codes table for distributed kill switch

Revision ID: add_halt_codes
Revises: add_is_admin_to_users
Create Date: 2026-04-09 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "add_halt_codes"
down_revision = "add_is_admin_to_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "halt_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("trustee_name", sa.String(), nullable=False),
        sa.Column("trustee_email", sa.String(), nullable=True),
        sa.Column("is_master", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("halt_codes")
