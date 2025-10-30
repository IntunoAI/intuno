"""Registry domain repository."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.registry import Agent


class RegistryRepository:
    """Repository for registry domain operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_agent(self, agent: Agent) -> Agent:
        """Create a new agent."""
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def get_agent_by_id(self, agent_id: UUID) -> Optional[Agent]:
        """Get agent by ID."""
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities), selectinload(Agent.requirements))
            .where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_agent_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent_id string."""
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities), selectinload(Agent.requirements))
            .where(Agent.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agents_by_user_id(self, user_id: UUID) -> List[Agent]:
        """Get all agents for a user."""
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities), selectinload(Agent.requirements))
            .where(Agent.user_id == user_id)
        )
        return list(result.scalars().all())

    async def search_agents(
        self,
        tags: Optional[List[str]] = None,
        capability: Optional[str] = None,
        search_text: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Agent]:
        """Search agents with filters."""
        query = select(Agent).options(selectinload(Agent.capabilities)).where(Agent.is_active)
        
        if tags:
            query = query.where(Agent.tags.overlap(tags))
        
        if capability:
            # This would need a join with capabilities table
            # For now, we'll implement basic search
            pass
        
        if search_text:
            query = query.where(
                Agent.name.ilike(f"%{search_text}%") |
                Agent.description.ilike(f"%{search_text}%")
            )
        
        query = query.offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def semantic_search(
        self,
        embedding: List[float],
        limit: int = 10,
    ) -> List[Agent]:
        """Semantic search using vector similarity."""
        # This would use pgvector's similarity search
        # For now, return empty list - will implement after pgvector setup
        return []

    async def update_agent(self, agent: Agent) -> Agent:
        """Update agent."""
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete agent by ID."""
        result = await self.session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent:
            await self.session.delete(agent)
            await self.session.commit()
            return True
        return False
