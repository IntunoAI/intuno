"""add pricing_enabled to agents

Revision ID: add_pricing_enabled
Revises: 8848633307e2
Create Date: 2026-03-26 00:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "add_pricing_enabled"
down_revision = "8848633307e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "pricing_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "pricing_enabled")
