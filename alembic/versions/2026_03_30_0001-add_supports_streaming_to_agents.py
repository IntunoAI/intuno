"""add supports_streaming to agents

Revision ID: add_supports_streaming
Revises: 82c36691dae3
Create Date: 2026-03-30 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_supports_streaming"
down_revision = "82c36691dae3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "supports_streaming",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "supports_streaming")
