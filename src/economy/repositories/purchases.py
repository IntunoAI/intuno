import uuid

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.economy.models.credit_purchase import CreditPurchase


class PurchaseRepository:
    """Persistence layer for credit purchase records."""

    def __init__(self, db_session: AsyncSession = Depends(get_session)):
        self.db_session = db_session

    async def create(self, purchase: CreditPurchase) -> CreditPurchase:
        self.db_session.add(purchase)
        await self.db_session.flush()
        await self.db_session.refresh(purchase)
        return purchase

    async def get_by_id(self, purchase_id: uuid.UUID) -> CreditPurchase | None:
        result = await self.db_session.execute(
            select(CreditPurchase).where(CreditPurchase.id == purchase_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        purchase_id: uuid.UUID,
        status: str,
        provider_reference: str | None = None,
    ) -> None:
        values: dict = {"status": status}
        if provider_reference is not None:
            values["provider_reference"] = provider_reference
        await self.db_session.execute(
            update(CreditPurchase)
            .where(CreditPurchase.id == purchase_id)
            .values(**values)
        )

    async def list_by_wallet(
        self,
        wallet_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CreditPurchase]:
        result = await self.db_session.execute(
            select(CreditPurchase)
            .where(CreditPurchase.wallet_id == wallet_id)
            .order_by(CreditPurchase.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
