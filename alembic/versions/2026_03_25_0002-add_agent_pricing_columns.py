"""Add pricing_strategy and base_price columns to agents table.

Revision ID: add_agent_pricing_cols
Revises: wallet_user_agent_split
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_agent_pricing_cols"
down_revision: Union[str, Sequence[str], None] = "wallet_user_agent_split"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("pricing_strategy", sa.String(), nullable=True))
    op.add_column("agents", sa.Column("base_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("agents", "base_price")
    op.drop_column("agents", "pricing_strategy")
