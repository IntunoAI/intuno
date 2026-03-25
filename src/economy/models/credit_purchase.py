import uuid

from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.economy.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CreditPurchase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks a credit purchase through its lifecycle.

    Simulates a Stripe-like checkout flow:
    ``pending`` -> ``completed`` (credits granted) or ``failed`` / ``refunded``.
    """

    __tablename__ = "credit_purchases"

    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id", ondelete="CASCADE"),
        nullable=False,
    )
    package_id: Mapped[str] = mapped_column(String(50), nullable=False)
    credits_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), server_default="pending", nullable=False,
    )
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    wallet: Mapped["Wallet"] = relationship("Wallet", lazy="selectin")
