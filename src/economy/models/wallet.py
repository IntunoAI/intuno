import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Index,
    Integer,
    String,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.economy.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Wallet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Holds a credit balance for a user or an individual agent.

    * **User wallets** (`wallet_type='user'`): the owner's main spending /
      receiving balance.  Exactly one per user.
    * **Agent wallets** (`wallet_type='agent'`): per-agent earnings ledger.
      Exactly one per agent.  Balances can be swept into the owner's user
      wallet via the consolidation endpoint.

    Uses integer credits to avoid floating-point rounding.  The settlement
    interface is abstract so it can later be swapped for x402 stablecoins.
    """

    __tablename__ = "wallets"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=True,
    )
    wallet_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="user",
    )  # "user" | "agent"
    balance: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="wallet")
    agent: Mapped[Optional["Agent"]] = relationship("Agent", back_populates="wallet")
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="wallet",
        order_by="Transaction.created_at.desc()",
        lazy="selectin",
    )

    __table_args__ = (
        # Exactly one owner must be set
        CheckConstraint(
            "(user_id IS NOT NULL AND agent_id IS NULL) OR "
            "(user_id IS NULL AND agent_id IS NOT NULL)",
            name="ck_wallets_one_owner",
        ),
        # One user-wallet per user
        Index(
            "uq_wallets_user_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
        # One agent-wallet per agent
        Index(
            "uq_wallets_agent_id",
            "agent_id",
            unique=True,
            postgresql_where=text("agent_id IS NOT NULL"),
        ),
    )


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An immutable ledger entry recording a credit or debit against a wallet.

    Double-entry bookkeeping: every transfer creates two Transaction rows
    (one debit, one credit) sharing the same ``reference_id``.
    """

    __tablename__ = "transactions"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    wallet: Mapped["Wallet"] = relationship("Wallet", back_populates="transactions")
