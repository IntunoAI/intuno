import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.economy.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Wallet(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Holds the credit balance for a single agent.

    Uses integer credits to avoid floating-point rounding.  The settlement
    interface is abstract so it can later be swapped for x402 stablecoins.
    """

    __tablename__ = "wallets"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    balance: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    agent: Mapped["Agent"] = relationship("Agent", back_populates="wallet")
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction",
        back_populates="wallet",
        order_by="Transaction.created_at.desc()",
        lazy="selectin",
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
