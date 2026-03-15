"""Registry domain repository."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.registry import Agent, AgentCredential, AgentRating
from src.database import get_db
from fastapi import Depends


class RegistryRepository:
    """Repository for registry domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create_agent(self, agent: Agent) -> Agent:
        """Create a new agent."""
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def get_agent_by_id(self, agent_id: UUID) -> Optional[Agent]:
        """Get agent by UUID."""
        result = await self.session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agent_by_agent_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent_id string."""
        result = await self.session.execute(
            select(Agent).where(Agent.agent_id == agent_id)
        )
        return result.scalar_one_or_none()

    async def get_agents_by_user_id(self, user_id: UUID) -> List[Agent]:
        """Get all agents for a user."""
        result = await self.session.execute(
            select(Agent).where(Agent.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_agents_by_ids(self, agent_ids: List[UUID]) -> List[Agent]:
        """Get agents by IDs, preserving order. Only returns active agents."""
        if not agent_ids:
            return []
        result = await self.session.execute(
            select(Agent).where(Agent.id.in_(agent_ids), Agent.is_active)
        )
        agents = {a.id: a for a in result.scalars().all()}
        return [agents[aid] for aid in agent_ids if aid in agents]

    async def list_agents(
        self,
        tags: Optional[List[str]] = None,
        search_text: Optional[str] = None,
        category: Optional[str] = None,
        sort: str = "created_at",
        order: str = "desc",
        days: Optional[int] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Agent]:
        """Search agents with filters and optional sort/order/days."""
        query = select(Agent).where(Agent.is_active)

        if tags:
            query = query.where(Agent.tags.overlap(tags))

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
        """Semantic discovery using vector similarity with Qdrant.

        Searches the agents collection directly and fetches full Agent objects.

        :param embedding: Query embedding vector
        :param limit: Maximum number of results
        :param similarity_threshold: Maximum cosine distance. None = no threshold.
        :return: List of (agent, distance) tuples ordered by similarity
        """
        from src.utilities.qdrant_service import QdrantService

        qdrant_service = QdrantService()

        results = await qdrant_service.search_similar(
            query_vector=embedding,
            limit=limit,
            similarity_threshold=similarity_threshold,
            filter_conditions={"is_active": True},
        )

        if not results:
            return []

        agent_ids = [r["id"] for r in results]
        distance_dict = {r["id"]: r["distance"] for r in results}

        query = select(Agent).where(Agent.id.in_(agent_ids))
        db_result = await self.session.execute(query)
        agents = list(db_result.scalars().all())
        agent_dict = {agent.id: agent for agent in agents}

        return [
            (agent_dict[aid], distance_dict[aid])
            for aid in agent_ids
            if aid in agent_dict and distance_dict.get(aid) is not None
        ]

    async def update_agent(self, agent: Agent) -> Agent:
        """Persist agent changes."""
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def delete_agent(self, agent_id: UUID) -> bool:
        """Delete agent by UUID."""
        result = await self.session.execute(
            select(Agent).where(Agent.id == agent_id)
        )
        agent = result.scalar_one_or_none()
        if agent:
            await self.session.delete(agent)
            await self.session.commit()
            return True
        return False

    # --- Agent ratings ---

    async def upsert_rating(
        self,
        user_id: UUID,
        agent_uuid: UUID,
        score: int,
        comment: Optional[str] = None,
    ) -> AgentRating:
        """Create or update a user's rating for an agent."""
        result = await self.session.execute(
            select(AgentRating).where(
                AgentRating.user_id == user_id,
                AgentRating.agent_id == agent_uuid,
            )
        )
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
            score=score,
            comment=comment,
        )
        self.session.add(rating)
        await self.session.commit()
        await self.session.refresh(rating)
        return rating

    async def get_rating_aggregate(self, agent_uuid: UUID) -> Tuple[Optional[float], int]:
        """Get average score and count of ratings for an agent."""
        result = await self.session.execute(
            select(
                func.avg(AgentRating.score).label("avg_score"),
                func.count(AgentRating.id).label("count"),
            ).where(AgentRating.agent_id == agent_uuid)
        )
        row = result.one()
        avg_score = float(row.avg_score) if row.avg_score is not None else None
        count = row.count or 0
        return (avg_score, count)

    async def get_ratings_for_agent(
        self, agent_uuid: UUID, limit: int = 20, offset: int = 0
    ) -> List[AgentRating]:
        """List ratings for an agent (recent first)."""
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
        """Get average score and count of ratings for multiple agents."""
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
        out: Dict[UUID, Tuple[Optional[float], int]] = {aid: (None, 0) for aid in agent_uuids}
        for row in rows:
            avg_score = float(row.avg_score) if row.avg_score is not None else None
            out[row.agent_id] = (avg_score, row.count or 0)
        return out

    # --- Agent credentials ---

    async def get_agent_credential(
        self, agent_id: UUID, credential_type: str
    ) -> Optional[AgentCredential]:
        """Get credential for an agent by type."""
        result = await self.session.execute(
            select(AgentCredential).where(
                AgentCredential.agent_id == agent_id,
                AgentCredential.credential_type == credential_type,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_agent_credential(
        self,
        agent_id: UUID,
        credential_type: str,
        encrypted_value: str,
        auth_header: Optional[str] = None,
        auth_scheme: Optional[str] = None,
    ) -> AgentCredential:
        """Set or update credential for an agent."""
        result = await self.session.execute(
            select(AgentCredential).where(
                AgentCredential.agent_id == agent_id,
                AgentCredential.credential_type == credential_type,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.encrypted_value = encrypted_value
            existing.auth_header = auth_header
            existing.auth_scheme = auth_scheme
            await self.session.commit()
            await self.session.refresh(existing)
            return existing
        cred = AgentCredential(
            agent_id=agent_id,
            credential_type=credential_type,
            encrypted_value=encrypted_value,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
        )
        self.session.add(cred)
        await self.session.commit()
        await self.session.refresh(cred)
        return cred

    async def delete_agent_credentials(self, agent_id: UUID) -> int:
        """Delete all credentials for an agent."""
        result = await self.session.execute(
            select(AgentCredential).where(AgentCredential.agent_id == agent_id)
        )
        creds = result.scalars().all()
        for c in creds:
            await self.session.delete(c)
        await self.session.commit()
        return len(creds)

    async def has_credentials(self, agent_id: UUID, auth_type: str) -> bool:
        """Return True if the agent has a credential matching its auth_type with a real value."""
        if auth_type == "public":
            return True
        result = await self.session.execute(
            select(AgentCredential.id).where(
                AgentCredential.agent_id == agent_id,
                AgentCredential.credential_type == auth_type,
                AgentCredential.encrypted_value.isnot(None),
                AgentCredential.encrypted_value != "",
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_credential_status_bulk(self, agent_auth_types: Dict[UUID, str]) -> Dict[UUID, bool]:
        """Return a mapping of agent UUID → whether a matching real credential exists."""
        if not agent_auth_types:
            return {}

        out: Dict[UUID, bool] = {
            aid: True for aid, auth_type in agent_auth_types.items() if auth_type == "public"
        }

        non_public = {aid: auth_type for aid, auth_type in agent_auth_types.items() if auth_type != "public"}
        if not non_public:
            return out

        rows = await self.session.execute(
            select(AgentCredential.agent_id, AgentCredential.credential_type)
            .where(
                AgentCredential.agent_id.in_(non_public.keys()),
                AgentCredential.encrypted_value.isnot(None),
                AgentCredential.encrypted_value != "",
            )
        )
        valid_creds = {(row[0], row[1]) for row in rows}

        for aid, auth_type in non_public.items():
            out[aid] = (aid, auth_type) in valid_creds

        return out
