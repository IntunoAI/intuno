"""Split wallets into user-level and agent-level wallets.

Add user_id and wallet_type columns to the wallets table, make agent_id
nullable, and migrate existing user wallets (where agent_id pointed at a
user rather than an agent) to use the new user_id column.

Revision ID: wallet_user_agent_split
Revises: add_brand_details_col
Create Date: 2026-03-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "wallet_user_agent_split"
down_revision: Union[str, Sequence[str], None] = "add_brand_details_col"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns
    op.add_column(
        "wallets",
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "wallets",
        sa.Column("wallet_type", sa.String(20), server_default="user", nullable=False),
    )

    # 2. Make agent_id nullable
    op.alter_column("wallets", "agent_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)

    # 3. Data migration: wallets whose agent_id matches a users.id are user wallets
    op.execute(
        """
        UPDATE wallets
        SET user_id = agent_id,
            agent_id = NULL,
            wallet_type = 'user'
        WHERE agent_id IN (SELECT id FROM users)
        """
    )

    # 4. Remaining wallets (agent_id points to a real agent) are agent wallets
    op.execute(
        """
        UPDATE wallets
        SET wallet_type = 'agent'
        WHERE agent_id IS NOT NULL
        """
    )

    # 5. Add FK constraint for user_id
    op.create_foreign_key(
        "fk_wallets_user_id",
        "wallets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 6. Drop the old plain unique constraint on agent_id
    op.drop_constraint("wallets_agent_id_key", "wallets", type_="unique")

    # 7. Add partial unique indexes
    op.create_index(
        "uq_wallets_user_id",
        "wallets",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_wallets_agent_id",
        "wallets",
        ["agent_id"],
        unique=True,
        postgresql_where=sa.text("agent_id IS NOT NULL"),
    )

    # 8. Add check constraint: exactly one owner
    op.create_check_constraint(
        "ck_wallets_one_owner",
        "wallets",
        "(user_id IS NOT NULL AND agent_id IS NULL) OR "
        "(user_id IS NULL AND agent_id IS NOT NULL)",
    )


def downgrade() -> None:
    # Reverse in opposite order
    op.drop_constraint("ck_wallets_one_owner", "wallets", type_="check")
    op.drop_index("uq_wallets_agent_id", table_name="wallets")
    op.drop_index("uq_wallets_user_id", table_name="wallets")

    # Restore plain unique constraint on agent_id
    op.create_unique_constraint("wallets_agent_id_key", "wallets", ["agent_id"])

    # Move user wallets back: set agent_id = user_id
    op.execute(
        """
        UPDATE wallets
        SET agent_id = user_id
        WHERE wallet_type = 'user' AND user_id IS NOT NULL
        """
    )

    op.drop_constraint("fk_wallets_user_id", "wallets", type_="foreignkey")

    # Make agent_id non-nullable again
    op.alter_column("wallets", "agent_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)

    # Drop new columns
    op.drop_column("wallets", "wallet_type")
    op.drop_column("wallets", "user_id")
