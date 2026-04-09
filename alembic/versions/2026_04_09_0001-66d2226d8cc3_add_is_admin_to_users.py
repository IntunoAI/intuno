"""add is_admin column to users table

Revision ID: 66d2226d8cc3
Revises: df05a2cb4da2
Create Date: 2026-04-09 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "66d2226d8cc3"
down_revision = "df05a2cb4da2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
