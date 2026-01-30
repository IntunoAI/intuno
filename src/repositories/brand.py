"""Brand repository."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.brand import Brand


class BrandRepository:
    """Repository for brand operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create(self, brand: Brand) -> Brand:
        """
        Create a new brand.
        :param brand: Brand
        :return: Brand
        """
        self.session.add(brand)
        await self.session.commit()
        await self.session.refresh(brand)
        return brand

    async def get_by_id(self, brand_id: UUID) -> Optional[Brand]:
        """
        Get brand by ID.
        :param brand_id: UUID
        :return: Optional[Brand]
        """
        result = await self.session.execute(
            select(Brand).where(Brand.id == brand_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Brand]:
        """
        Get brand by slug.
        :param slug: str
        :return: Optional[Brand]
        """
        result = await self.session.execute(
            select(Brand).where(Brand.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_by_owner_id(self, owner_id: UUID) -> List[Brand]:
        """
        List brands owned by user.
        :param owner_id: UUID
        :return: List[Brand]
        """
        result = await self.session.execute(
            select(Brand).where(Brand.owner_id == owner_id).order_by(Brand.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, brand: Brand) -> Brand:
        """
        Update brand.
        :param brand: Brand
        :return: Brand
        """
        await self.session.commit()
        await self.session.refresh(brand)
        return brand
