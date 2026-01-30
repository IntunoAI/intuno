"""Broker persistence: broker_config (invocation log lives in InvocationLogRepository)."""

from typing import Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.broker import BrokerConfig


class BrokerConfigRepository:
    """Repository for broker config (per-integration or global)."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def get_global_config(self) -> Optional[BrokerConfig]:
        """
        Get global broker config (integration_id is None).
        :return: Optional[BrokerConfig]
        """
        result = await self.session.execute(
            select(BrokerConfig).where(BrokerConfig.integration_id.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_config_for_integration(
        self, integration_id: UUID
    ) -> Optional[BrokerConfig]:
        """
        Get broker config for an integration.
        :param integration_id: UUID
        :return: Optional[BrokerConfig]
        """
        result = await self.session.execute(
            select(BrokerConfig).where(BrokerConfig.integration_id == integration_id)
        )
        return result.scalar_one_or_none()

    async def get_effective_config(
        self, integration_id: Optional[UUID]
    ) -> Optional[BrokerConfig]:
        """
        Get effective config: integration override if present, else global.
        :param integration_id: Optional[UUID]
        :return: Optional[BrokerConfig]
        """
        if integration_id is not None:
            config = await self.get_config_for_integration(integration_id)
            if config is not None:
                return config
        return await self.get_global_config()

    async def upsert_config(self, config: BrokerConfig) -> BrokerConfig:
        """
        Create or update a broker config.
        :param config: BrokerConfig
        :return: BrokerConfig
        """
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config
