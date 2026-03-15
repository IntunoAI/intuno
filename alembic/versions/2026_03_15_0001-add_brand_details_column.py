"""add brand_details column

Revision ID: add_brand_details_col
Revises: 5e324d95153f
Create Date: 2026-03-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_brand_details_col"
down_revision: Union[str, Sequence[str], None] = "5e324d95153f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brands", sa.Column("brand_details", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("brands", "brand_details")
