"""Agent config domain repository."""

from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.database import get_db
from agents.models.agent_config import AgentConfig


class AgentConfigRepository:
    """Repository for agent config domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def get_by_name(self, name: str) -> Optional[AgentConfig]:
        """
        Get agent config by name.
        :param name: Agent config name
        :return: Optional[AgentConfig]
        """
        result = await self.session.execute(
            select(AgentConfig).where(AgentConfig.name == name)
        )
        return result.scalar_one_or_none()

    async def create(self, agent_config: AgentConfig) -> AgentConfig:
        """
        Create a new agent config.
        :param agent_config: AgentConfig
        :return: AgentConfig
        """
        self.session.add(agent_config)
        await self.session.commit()
        await self.session.refresh(agent_config)
        return agent_config
