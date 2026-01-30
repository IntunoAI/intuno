"""Integration domain repository."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models.integration import Integration


class IntegrationRepository:
    """Repository for integration domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create(self, integration: Integration) -> Integration:
        """Create a new integration."""
        self.session.add(integration)
        await self.session.commit()
        await self.session.refresh(integration)
        return integration

    async def get_by_id(self, integration_id: UUID) -> Optional[Integration]:
        """Get integration by ID (with api_keys loaded for detail)."""
        result = await self.session.execute(
            select(Integration)
            .where(Integration.id == integration_id)
            .options(selectinload(Integration.api_keys))
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> List[Integration]:
        """Get all integrations for a user (with api_keys loaded for has_api_key hint)."""
        result = await self.session.execute(
            select(Integration)
            .where(Integration.user_id == user_id)
            .order_by(Integration.created_at.desc())
            .options(selectinload(Integration.api_keys))
        )
        return list(result.scalars().all())

    async def delete(self, integration_id: UUID) -> bool:
        """Delete integration by ID."""
        result = await self.session.execute(
            select(Integration).where(Integration.id == integration_id)
        )
        integration = result.scalar_one_or_none()
        if integration:
            await self.session.delete(integration)
            await self.session.commit()
            return True
        return False
