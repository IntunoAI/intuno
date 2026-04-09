"""add is_admin column to users table

Revision ID: add_is_admin_to_users
Revises: add_communication_networks
Create Date: 2026-04-09 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_is_admin_to_users"
down_revision = "add_communication_networks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
