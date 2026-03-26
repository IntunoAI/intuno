import uuid

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.economy.models.order import Order, Trade


class MarketRepository:
    """Persistence layer for orders and trades."""

    def __init__(self, db_session: AsyncSession = Depends(get_session)):
        self.db_session = db_session

    # ── Orders ──────────────────────────────────────────────

    async def create_order(self, order: Order) -> Order:
        """Insert a new order and return the persisted instance."""
        self.db_session.add(order)
        await self.db_session.flush()
        await self.db_session.refresh(order)
        return order

    async def get_order_by_id(self, order_id: uuid.UUID) -> Order | None:
        """Return an order by primary key."""
        result = await self.db_session.execute(
            select(Order).where(Order.id == order_id)
        )
        return result.scalar_one_or_none()

    async def list_open_orders(
        self,
        capability: str | None = None,
        side: str | None = None,
        limit: int = 100,
    ) -> list[Order]:
        """Return open orders, optionally filtered by capability and side."""
        query = (
            select(Order)
            .where(Order.status == "open")
            .order_by(Order.created_at.asc())
        )
        if capability:
            query = query.where(Order.capability == capability)
        if side:
            query = query.where(Order.side == side)
        query = query.limit(limit)
        result = await self.db_session.execute(query)
        return list(result.scalars().all())

    async def update_order_status(
        self, order_id: uuid.UUID, status: str,
    ) -> None:
        """Set the status of an order (e.g. open -> filled)."""
        await self.db_session.execute(
            update(Order).where(Order.id == order_id).values(status=status)
        )

    # ── Trades ──────────────────────────────────────────────

    async def create_trade(self, trade: Trade) -> Trade:
        """Insert a trade record and return it."""
        self.db_session.add(trade)
        await self.db_session.flush()
        await self.db_session.refresh(trade)
        return trade

    async def list_trades(
        self,
        capability: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Trade]:
        """Return recent trades, newest first."""
        query = select(Trade).order_by(Trade.created_at.desc())
        if capability:
            query = query.where(Trade.capability == capability)
        query = query.limit(limit).offset(offset)
        result = await self.db_session.execute(query)
        return list(result.scalars().all())

    async def count_trades(self) -> int:
        """Return the total number of trades."""
        from sqlalchemy import func
        result = await self.db_session.execute(
            select(func.count()).select_from(Trade)
        )
        return result.scalar_one()

    async def total_volume(self) -> int:
        """Return the sum of all trade prices."""
        from sqlalchemy import func
        result = await self.db_session.execute(
            select(func.coalesce(func.sum(Trade.price), 0))
        )
        return result.scalar_one()
