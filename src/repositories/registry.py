"""Registry domain repository."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.registry import Agent, AgentRating, Capability, AgentRequirement
from src.database import get_db
from fastapi import Depends


class RegistryRepository:
    """Repository for registry domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create_agent(self, agent: Agent) -> Agent:
        """Create a new agent.
        :param agent: Agent
        :return: Agent
        """
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def get_agent_by_id(self, agent_id: UUID) -> Optional[Agent]:
        """Get agent by ID.
        :param agent_id: UUID
        :return: Optional[Agent]
        """
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities), selectinload(Agent.requirements))
            .where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_agent_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent_id string.
        :param agent_id: str
        :return: Optional[Agent]
        """
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities), selectinload(Agent.requirements))
            .where(Agent.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agents_by_user_id(self, user_id: UUID) -> List[Agent]:
        """Get all agents for a user.
        :param user_id: UUID
        :return: List[Agent]
        """
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities), selectinload(Agent.requirements))
            .where(Agent.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_agents_by_ids(self, agent_ids: List[UUID]) -> List[Agent]:
        """Get agents by IDs, preserving order. Only returns active agents.
        :param agent_ids: List[UUID]
        :return: List[Agent] in the same order as agent_ids (skips missing/inactive)
        """
        if not agent_ids:
            return []
        result = await self.session.execute(
            select(Agent)
            .options(selectinload(Agent.capabilities))
            .where(Agent.id.in_(agent_ids), Agent.is_active)
        )
        agents = {a.id: a for a in result.scalars().all()}
        return [agents[aid] for aid in agent_ids if aid in agents]

    async def list_agents(
        self,
        tags: Optional[List[str]] = None,
        capability: Optional[str] = None,
        search_text: Optional[str] = None,
        category: Optional[str] = None,
        sort: str = "created_at",
        order: str = "desc",
        days: Optional[int] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Agent]:
        """Search agents with filters and optional sort/order/days."""
        query = select(Agent).options(selectinload(Agent.capabilities)).where(Agent.is_active)

        if tags:
            query = query.where(Agent.tags.overlap(tags))

        if capability:
            # Would need join with capabilities; leave as no-op for now
            pass

        if search_text:
            query = query.where(
                Agent.name.ilike(f"%{search_text}%") | Agent.description.ilike(f"%{search_text}%")
            )

        if category is not None:
            query = query.where(Agent.category == category)

        if days is not None:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.where(Agent.created_at >= since)

        sort_column = getattr(Agent, sort, Agent.created_at)
        if sort not in ("created_at", "updated_at", "name"):
            sort_column = Agent.created_at
        if order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def semantic_discover(
        self,
        embedding: List[float],
        limit: int = 10,
        similarity_threshold: Optional[float] = None,
    ) -> List[Tuple[Agent, float]]:
        """
        Semantic discovery using vector similarity with Qdrant.
        Searches capabilities first for better precision, then aggregates to agents.
        Uses cosine distance to find the most similar agents.
        If similarity_threshold is provided, only returns agents below the threshold.
        :param embedding: List[float] - Query embedding vector
        :param limit: int - Maximum number of results
        :param similarity_threshold: Optional[float] - Maximum cosine distance (0.0=same, 2.0=opposite). None = no threshold.
        :return: List[tuple[Agent, float]] - List of (agent, distance) tuples ordered by similarity
        """
        from src.utilities.qdrant_service import QdrantService
        
        qdrant_service = QdrantService()
        
        # Search capabilities first for better precision
        # Use a higher limit to get more capability matches, then aggregate to agents
        capability_results = await qdrant_service.search_capabilities(
            query_vector=embedding,
            limit=limit * 3,  # Get more capability matches to aggregate
            similarity_threshold=similarity_threshold,
            filter_conditions={"is_active": True},
        )
        
        if not capability_results:
            # Fallback to agent-level search if no capability matches
            agent_results = await qdrant_service.search_similar(
                query_vector=embedding,
                limit=limit,
                similarity_threshold=similarity_threshold,
                filter_conditions={"is_active": True},
            )
            
            if not agent_results:
                return []
            
            agent_ids = [UUID(r["id"]) for r in agent_results]
            query = (
                select(Agent)
                .options(selectinload(Agent.capabilities))
                .where(Agent.id.in_(agent_ids))
            )
            result = await self.session.execute(query)
            agents = list(result.scalars().all())
            agent_dict = {agent.id: agent for agent in agents}
            distance_dict = {UUID(r["id"]): r["distance"] for r in agent_results}
            
            return [
                (agent_dict[aid], distance_dict[aid])
                for aid in agent_ids
                if aid in agent_dict and aid in distance_dict
            ]
        
        # Aggregate capability results to agents
        # Group by agent_uuid and take the best (lowest distance) match per agent
        agent_scores: Dict[UUID, float] = {}  # agent_id -> best_distance
        
        for cap_result in capability_results:
            agent_uuid_str = cap_result["payload"].get("agent_uuid")
            if not agent_uuid_str:
                continue
            
            try:
                agent_uuid = UUID(agent_uuid_str)
                distance = cap_result["distance"]
                
                # Keep the best (lowest distance) match for each agent
                if agent_uuid not in agent_scores or distance < agent_scores[agent_uuid]:
                    agent_scores[agent_uuid] = distance
            except (ValueError, TypeError):
                continue
        
        if not agent_scores:
            return []
        
        # Sort agents by distance and limit results
        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1])[:limit]
        agent_ids = [aid for aid, _ in sorted_agents]
        
        # Fetch full Agent objects from PostgreSQL
        query = (
            select(Agent)
            .options(selectinload(Agent.capabilities))
            .where(Agent.id.in_(agent_ids))
        )
        
        result = await self.session.execute(query)
        agents = list(result.scalars().all())
        
        # Create a mapping of agent ID to agent
        agent_dict = {agent.id: agent for agent in agents}
        
        # Return agents with their similarity scores, maintaining sorted order
        return [
            (agent_dict[aid], agent_scores[aid])
            for aid, _ in sorted_agents
            if aid in agent_dict
        ]

    async def update_agent(self, agent: Agent) -> Agent:
        """Update agent."""
        await self.session.commit()
        await self.session.refresh(agent)
        return agent
    
    async def update_capability(self, capability: Capability) -> Capability:
        """Update capability."""
        await self.session.commit()
        await self.session.refresh(capability)
        return capability

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

    async def add_capabilities(self, capabilities: List[Capability]) -> None:
        """
        Add capabilities to the database.
        :param capabilities: List[Capability]
        :return: None
        """
        for capability in capabilities:
            self.session.add(capability)
        await self.session.commit()

    async def add_requirements(self, requirements: List[AgentRequirement]) -> None:
        """
        Add requirements to the database.
        :param requirements: List[AgentRequirement]
        :return: None
        """
        for requirement in requirements:
            self.session.add(requirement)
        await self.session.commit()

    async def get_agent_capabilities(self, agent_id: UUID) -> List[Capability]:
        """Get all capabilities for an agent.
        :param agent_id: UUID
        :return: List[Capability]
        """
        result = await self.session.execute(
            select(Capability).where(Capability.agent_id == agent_id)
        )
        return list(result.scalars().all())
    
    async def delete_agent_capabilities(self, agent_id: UUID) -> None:
        """
        Delete all capabilities for an agent.
        :param agent_id: UUID
        :return: None
        """
        result = await self.session.execute(
            select(Capability).where(Capability.agent_id == agent_id)
        )
        capabilities = result.scalars().all()
        for capability in capabilities:
            await self.session.delete(capability)
        await self.session.commit()

    async def delete_agent_requirements(self, agent_id: UUID) -> None:
        """
        Delete all requirements for an agent.
        :param agent_id: UUID
        :return: None
        """
        result = await self.session.execute(
            select(AgentRequirement).where(AgentRequirement.agent_id == agent_id)
        )
        requirements = result.scalars().all()
        for requirement in requirements:
            await self.session.delete(requirement)
        await self.session.commit()

    # --- Agent ratings ---

    async def upsert_rating(
        self,
        user_id: UUID,
        agent_uuid: UUID,
        score: int,
        capability_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> AgentRating:
        """
        Create or update a user's rating for an agent (or capability).
        :param user_id: UUID
        :param agent_uuid: UUID (agents.id)
        :param score: int 1-5
        :param capability_id: Optional[str]
        :param comment: Optional[str]
        :return: AgentRating
        """
        q = select(AgentRating).where(
            AgentRating.user_id == user_id,
            AgentRating.agent_id == agent_uuid,
        )
        if capability_id is None:
            q = q.where(AgentRating.capability_id.is_(None))
        else:
            q = q.where(AgentRating.capability_id == capability_id)
        result = await self.session.execute(q)
        existing = result.scalar_one_or_none()
        if existing:
            existing.score = score
            existing.comment = comment
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        rating = AgentRating(
            user_id=user_id,
            agent_id=agent_uuid,
            capability_id=capability_id,
            score=score,
            comment=comment,
        )
        self.session.add(rating)
        await self.session.commit()
        await self.session.refresh(rating)
        return rating

    async def get_rating_aggregate(self, agent_uuid: UUID) -> Tuple[Optional[float], int]:
        """
        Get average score and count of ratings for an agent.
        :param agent_uuid: UUID (agents.id)
        :return: Tuple[Optional[float], int]
        """
        result = await self.session.execute(
            select(func.avg(AgentRating.score).label("avg_score"), func.count(AgentRating.id).label("count")).where(
                AgentRating.agent_id == agent_uuid
            )
        )
        row = result.one()
        avg_score = float(row.avg_score) if row.avg_score is not None else None
        count = row.count or 0
        return (avg_score, count)

    async def get_ratings_for_agent(
        self, agent_uuid: UUID, limit: int = 20, offset: int = 0
    ) -> List[AgentRating]:
        """
        List ratings for an agent (recent first).
        :param agent_uuid: UUID (agents.id)
        :param limit: int
        :param offset: int
        :return: List[AgentRating]
        """
        result = await self.session.execute(
            select(AgentRating)
            .where(AgentRating.agent_id == agent_uuid)
            .order_by(AgentRating.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_rating_aggregates_bulk(
        self, agent_uuids: List[UUID]
    ) -> Dict[UUID, Tuple[Optional[float], int]]:
        """
        Get average score and count of ratings for multiple agents.
        :param agent_uuids: List[UUID]
        :return: Dict[UUID, Tuple[Optional[float], int]]
        """
        if not agent_uuids:
            return {}
        result = await self.session.execute(
            select(
                AgentRating.agent_id,
                func.avg(AgentRating.score).label("avg_score"),
                func.count(AgentRating.id).label("count"),
            )
            .where(AgentRating.agent_id.in_(agent_uuids))
            .group_by(AgentRating.agent_id)
        )
        rows = result.all()
        out: Dict[UUID, Tuple[Optional[float], int]] = {
            aid: (None, 0) for aid in agent_uuids
        }
        for row in rows:
            avg_score = float(row.avg_score) if row.avg_score is not None else None
            out[row.agent_id] = (avg_score, row.count or 0)
        return out
