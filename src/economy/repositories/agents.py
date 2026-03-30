import uuid

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.models.registry import Agent


class AgentRepository:
    """Persistence layer for agent records."""

    def __init__(self, db_session: AsyncSession = Depends(get_session)):
        self.db_session = db_session

    async def create(self, agent: Agent) -> Agent:
        """Insert a new agent and return the persisted instance."""
        self.db_session.add(agent)
        await self.db_session.flush()
        await self.db_session.refresh(agent)
        return agent

    async def get_by_id(self, agent_id: uuid.UUID) -> Agent | None:
        """Return an agent by primary key, or None."""
        result = await self.db_session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_by_agent_id(self, agent_id: str) -> Agent | None:
        """Return an agent by its human-readable agent_id string."""
        result = await self.db_session.execute(
            select(Agent).where(Agent.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        is_active: bool | None = None,
        capability: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Agent]:
        """Return a paginated list of agents with optional filters."""
        query = select(Agent).order_by(Agent.created_at.desc())
        if is_active is not None:
            query = query.where(Agent.is_active == is_active)
        if capability is not None:
            query = query.where(Agent.tags.any(capability))
        query = query.limit(limit).offset(offset)
        result = await self.db_session.execute(query)
        return list(result.scalars().all())

    async def update(self, agent_id: uuid.UUID, values: dict) -> Agent | None:
        """Apply a partial update and return the refreshed agent."""
        await self.db_session.execute(
            update(Agent).where(Agent.id == agent_id).values(**values)
        )
        return await self.get_by_id(agent_id)

    async def delete(self, agent_id: uuid.UUID) -> bool:
        """Delete an agent by primary key. Returns True if a row was removed."""
        agent = await self.get_by_id(agent_id)
        if not agent:
            return False
        await self.db_session.delete(agent)
        await self.db_session.flush()
        return True
