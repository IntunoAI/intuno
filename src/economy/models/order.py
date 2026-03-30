import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base
from src.economy.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A bid (buy) or ask (sell) on the marketplace.

    ``side`` is either ``'bid'`` or ``'ask'``.
    ``status`` tracks the lifecycle: ``open`` -> ``filled`` | ``cancelled``.
    """

    __tablename__ = "orders"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(10), nullable=False)
    capability: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), server_default="open", nullable=False,
    )
    tick: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    agent: Mapped["Agent"] = relationship("Agent", lazy="selectin")


class Trade(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A completed match between a bid and an ask.

    Records the buyer, seller, execution price, and outcome of the
    simulated service delivery.
    """

    __tablename__ = "trades"

    bid_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    ask_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    buyer_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    seller_agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), server_default="settled", nullable=False,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    tick: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    bid_order: Mapped["Order"] = relationship("Order", foreign_keys=[bid_order_id], lazy="selectin")
    ask_order: Mapped["Order"] = relationship("Order", foreign_keys=[ask_order_id], lazy="selectin")
    buyer_agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[buyer_agent_id], lazy="selectin")
    seller_agent: Mapped["Agent"] = relationship("Agent", foreign_keys=[seller_agent_id], lazy="selectin")
