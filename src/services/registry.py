"""Registry domain service."""

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import Depends

from src.core.credential_crypto import encrypt_credential
from src.core.url_validation import validate_invoke_endpoint
from src.repositories.brand import BrandRepository
from src.models.registry import Agent, AgentRating
from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.registry import RegistryRepository
from src.schemas.registry import AgentRegistration, AgentSearchQuery, AgentUpdate, DiscoverQuery
from src.utilities.embedding import EmbeddingService
from src.utilities.qdrant_service import QdrantService
from src.utilities.semantic_enhancement import SemanticEnhancementService
from src.core.settings import settings


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _generate_agent_id(name: str) -> str:
    """Generate a unique agent_id from name + short UUID."""
    slug = _slugify(name)
    short_id = str(uuid4()).replace("-", "")[:8]
    return f"{slug}-{short_id}"


class RegistryService:
    """Service for agent registry operations."""

    def __init__(
        self,
        registry_repository: RegistryRepository = Depends(),
        invocation_log_repository: InvocationLogRepository = Depends(),
        embedding_service: EmbeddingService = Depends(),
        brand_repository: BrandRepository = Depends(),
    ):
        self.registry_repository = registry_repository
        self.invocation_log_repository = invocation_log_repository
        self.embedding_service = embedding_service
        self.brand_repository = brand_repository
        self.qdrant_service = QdrantService()
        self.semantic_enhancement = SemanticEnhancementService(
            enabled=settings.ENABLE_LLM_ENHANCEMENT,
            model=settings.LLM_ENHANCEMENT_MODEL,
        )

    async def register_agent(
        self,
        registration: AgentRegistration,
        user_id: UUID,
        enhance: bool = True,
    ) -> Agent:
        """Register a new agent.

        :param registration: AgentRegistration
        :param user_id: UUID of the registering user
        :param enhance: Whether to enhance text with LLM before embedding
        :return: Created Agent
        """
        brand_id = registration.brand_id

        # If brand_id provided, ensure user owns the brand
        if brand_id is not None:
            brand = await self.brand_repository.get_by_id(brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Brand not found or you are not the owner")

        # Validate invoke_endpoint (SSRF protection)
        allowed = [h.strip() for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",") if h.strip()]
        validate_invoke_endpoint(registration.endpoint, allowed_hosts=allowed if allowed else None)

        # Auto-generate unique agent_id
        agent_id = _generate_agent_id(registration.name)

        # Generate embedding
        if enhance:
            agent_embedding = await self.embedding_service.generate_enhanced_embedding(
                agent_name=registration.name,
                description=registration.description,
                tags=registration.tags,
                input_schema=registration.input_schema,
            )
        else:
            agent_text = self.embedding_service.prepare_agent_text_for_embedding(
                registration.name,
                registration.description,
                registration.tags,
                registration.input_schema,
            )
            agent_embedding = await self.embedding_service.generate_embedding(agent_text)

        # Create agent
        agent = Agent(
            agent_id=agent_id,
            user_id=user_id,
            brand_id=brand_id,
            name=registration.name,
            description=registration.description,
            version="1.0.0",
            invoke_endpoint=registration.endpoint,
            auth_type=registration.auth_type,
            input_schema=registration.input_schema,
            tags=registration.tags,
            category=registration.category,
            trust_verification="self-signed",
            qdrant_point_id=None,
        )

        created_agent = await self.registry_repository.create_agent(agent)

        # Store embedding in Qdrant
        await self.qdrant_service.upsert_vector(
            point_id=created_agent.id,
            vector=agent_embedding,
            payload={
                "agent_id": agent_id,
                "is_active": True,
                "name": registration.name,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )

        created_agent.qdrant_point_id = created_agent.id
        created_agent.embedding_version = settings.EMBEDDING_VERSION
        await self.registry_repository.update_agent(created_agent)

        return await self.registry_repository.get_agent_by_id(created_agent.id)

    async def list_agents(self, query: AgentSearchQuery) -> List[Agent]:
        """Search agents with filters."""
        return await self.registry_repository.list_agents(
            tags=query.tags,
            search_text=query.search,
            category=query.category,
            sort=query.sort,
            order=query.order,
            days=query.days,
            limit=query.limit,
            offset=query.offset,
        )

    async def semantic_discover(
        self, query: DiscoverQuery, enhance_query: bool = True
    ) -> List[Tuple[Agent, float]]:
        """Semantic discovery using vector similarity with optional quality re-ranking.

        :param query: DiscoverQuery
        :param enhance_query: Whether to enhance query with LLM
        :return: List of (agent, distance) tuples
        """
        if enhance_query:
            enhanced_query_text = await self.semantic_enhancement.enhance_discovery_query(query.query)
        else:
            enhanced_query_text = query.query

        query_embedding = await self.embedding_service.generate_embedding(enhanced_query_text, enhance=False)

        results = await self.registry_repository.semantic_discover(
            embedding=query_embedding,
            limit=query.limit,
            similarity_threshold=query.similarity_threshold,
        )

        if not results or query.rank_by == "similarity_only":
            return results

        agent_ids = [agent.id for agent, _ in results]
        rating_aggregates = await self.registry_repository.get_rating_aggregates_bulk(agent_ids)
        quality_metrics = await self.invocation_log_repository.get_agent_quality_metrics_bulk(agent_ids)

        now = datetime.now(timezone.utc)
        scored: List[Tuple[Agent, float, float]] = []
        for agent, distance in results:
            similarity_norm = max(0.0, 1.0 - (distance / 2.0))

            rating_avg, rating_count = rating_aggregates.get(agent.id, (None, 0))
            success_rate, avg_latency_ms, inv_count = quality_metrics.get(agent.id, (None, None, 0))
            rating_norm = (rating_avg / 5.0) if rating_avg is not None else 0.0
            success_norm = success_rate if success_rate is not None else 0.0
            latency_norm = (1.0 / (1.0 + (avg_latency_ms or 0) / 1000.0)) if (avg_latency_ms is not None or inv_count) else 0.0
            quality_norm = rating_norm * 0.4 + success_norm * 0.4 + latency_norm * 0.2

            updated = agent.updated_at or agent.created_at
            updated_utc = updated if (getattr(updated, "tzinfo", None) and updated.tzinfo) else updated.replace(tzinfo=timezone.utc)
            days_ago = (now - updated_utc).days
            recency_norm = max(0.0, 1.0 - (days_ago / 90.0))

            if query.rank_by == "quality_first":
                composite = 0.2 * similarity_norm + 0.7 * quality_norm + 0.1 * recency_norm
            else:
                composite = 0.5 * similarity_norm + 0.35 * quality_norm + 0.15 * recency_norm

            scored.append((agent, distance, composite))

        scored.sort(key=lambda x: x[2], reverse=True)
        return [(agent, distance) for agent, distance, _ in scored]

    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent_id string."""
        return await self.registry_repository.get_agent_by_agent_id(agent_id)

    async def get_agent_by_uuid(self, agent_uuid: UUID) -> Optional[Agent]:
        """Get agent by UUID."""
        return await self.registry_repository.get_agent_by_id(agent_uuid)

    async def update_agent(
        self,
        agent_uuid: UUID,
        update: AgentUpdate,
        user_id: UUID,
        enhance: bool = True,
    ) -> Agent:
        """Update an agent (owner or brand owner only).

        Only provided fields are updated (partial update).
        """
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            raise ValueError("Agent not found")

        # Authorization: owner or brand owner
        if agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Not authorized to update this agent")
        elif agent.user_id != user_id:
            raise ValueError("Not authorized to update this agent")

        # Validate new brand if provided
        if update.brand_id is not None:
            brand = await self.brand_repository.get_by_id(update.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Brand not found or you are not the owner")
            agent.brand_id = update.brand_id

        # Validate new endpoint if provided
        if update.endpoint is not None:
            allowed = [h.strip() for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",") if h.strip()]
            validate_invoke_endpoint(update.endpoint, allowed_hosts=allowed if allowed else None)
            agent.invoke_endpoint = update.endpoint

        # Apply partial updates
        if update.name is not None:
            agent.name = update.name
        if update.description is not None:
            agent.description = update.description
        if update.auth_type is not None:
            agent.auth_type = update.auth_type
        if update.input_schema is not None:
            agent.input_schema = update.input_schema
        if update.tags is not None:
            agent.tags = update.tags
        if update.category is not None:
            agent.category = update.category

        # Regenerate embedding
        if enhance:
            agent_embedding = await self.embedding_service.generate_enhanced_embedding(
                agent_name=agent.name,
                description=agent.description,
                tags=agent.tags,
                input_schema=agent.input_schema,
            )
        else:
            agent_text = self.embedding_service.prepare_agent_text_for_embedding(
                agent.name, agent.description, agent.tags, agent.input_schema
            )
            agent_embedding = await self.embedding_service.generate_embedding(agent_text)

        qdrant_point_id = agent.qdrant_point_id or agent.id
        await self.qdrant_service.upsert_vector(
            point_id=qdrant_point_id,
            vector=agent_embedding,
            payload={
                "agent_id": agent.agent_id,
                "is_active": agent.is_active,
                "name": agent.name,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )
        agent.qdrant_point_id = qdrant_point_id
        agent.embedding_version = settings.EMBEDDING_VERSION

        return await self.registry_repository.update_agent(agent)

    async def set_agent_credential(
        self,
        agent_uuid: UUID,
        user_id: UUID,
        credential_type: str,
        value: str,
        auth_header: Optional[str] = None,
        auth_scheme: Optional[str] = None,
    ) -> None:
        """Set or update per-agent credential (owner or brand owner only)."""
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            raise ValueError("Agent not found")
        if agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Not authorized to set credentials for this agent")
        elif agent.user_id != user_id:
            raise ValueError("Not authorized to set credentials for this agent")
        encrypted = encrypt_credential(value)
        await self.registry_repository.upsert_agent_credential(
            agent_uuid,
            credential_type,
            encrypted,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
        )

    async def delete_agent_credentials(self, agent_uuid: UUID, user_id: UUID) -> int:
        """Delete all credentials for an agent (owner or brand owner only)."""
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            raise ValueError("Agent not found")
        if agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Not authorized to delete credentials for this agent")
        elif agent.user_id != user_id:
            raise ValueError("Not authorized to delete credentials for this agent")
        return await self.registry_repository.delete_agent_credentials(agent_uuid)

    async def delete_agent(self, agent_uuid: UUID, user_id: UUID) -> bool:
        """Delete an agent (owner or brand owner only)."""
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            return False

        if agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Not authorized to delete this agent")
        elif agent.user_id != user_id:
            raise ValueError("Not authorized to delete this agent")

        # Delete from Qdrant
        if agent.qdrant_point_id:
            try:
                await self.qdrant_service.delete_vector(agent.qdrant_point_id)
            except Exception:
                pass

        return await self.registry_repository.delete_agent(agent_uuid)

    async def get_agents_by_user_id(self, user_id: UUID) -> List[Agent]:
        """Get all agents for a user."""
        return await self.registry_repository.get_agents_by_user_id(user_id)

    async def rate_agent(
        self,
        agent_id: str,
        user_id: UUID,
        score: int,
        comment: Optional[str] = None,
    ) -> AgentRating:
        """Submit or update a user's rating for an agent."""
        agent = await self.registry_repository.get_agent_by_agent_id(agent_id)
        if not agent:
            raise ValueError("Agent not found")
        return await self.registry_repository.upsert_rating(
            user_id=user_id,
            agent_uuid=agent.id,
            score=score,
            comment=comment,
        )

    async def get_rating_aggregate(self, agent_uuid: UUID) -> Tuple[Optional[float], int]:
        """Get average rating and count for an agent."""
        return await self.registry_repository.get_rating_aggregate(agent_uuid)

    async def get_ratings_for_agent(
        self, agent_uuid: UUID, limit: int = 20, offset: int = 0
    ) -> List[AgentRating]:
        """List ratings for an agent (recent first)."""
        return await self.registry_repository.get_ratings_for_agent(
            agent_uuid, limit=limit, offset=offset
        )

    async def get_rating_aggregates_bulk(self, agent_uuids: List[UUID]) -> dict:
        """Get (rating_avg, rating_count) for multiple agents."""
        return await self.registry_repository.get_rating_aggregates_bulk(agent_uuids)

    async def get_agent_quality_metrics(
        self, agent_uuid: UUID, window_days: int = 90
    ) -> Tuple[Optional[float], Optional[float], int]:
        """Get quality metrics for an agent from invocation logs."""
        return await self.invocation_log_repository.get_agent_quality_metrics(
            agent_uuid, window_days=window_days
        )

    async def get_agent_quality_metrics_bulk(
        self, agent_uuids: List[UUID], window_days: int = 90
    ) -> Dict[UUID, Tuple[Optional[float], Optional[float], int]]:
        """Get quality metrics for multiple agents."""
        return await self.invocation_log_repository.get_agent_quality_metrics_bulk(
            agent_uuids, window_days=window_days
        )

    async def create_brand_agent(self, brand: "Brand") -> Optional[Agent]:
        """Create the default brand agent when a brand is verified. Idempotent."""
        agent_id = f"brand-{brand.slug}-{str(uuid4()).replace('-', '')[:8]}"
        existing = await self.registry_repository.get_agent_by_agent_id(f"brand-{brand.slug}-")
        # Check by name pattern instead
        agents = await self.registry_repository.get_agents_by_user_id(brand.owner_id)
        for a in agents:
            if a.is_brand_agent and a.brand_id == brand.id:
                return a

        placeholder_url = settings.BRAND_AGENT_PLACEHOLDER_URL
        tags = ["brand", brand.slug, "company", "contact"]
        name = f"{brand.name} – Official"
        description = brand.description or f"Official assistant for {brand.name}. Ask about the company, products, or contact."

        agent_text = self.embedding_service.prepare_agent_text_for_embedding(name, description, tags)
        agent_embedding = await self.embedding_service.generate_embedding(agent_text, enhance=False)

        agent = Agent(
            agent_id=agent_id,
            user_id=brand.owner_id,
            brand_id=brand.id,
            name=name,
            description=description,
            version="1.0.0",
            invoke_endpoint=placeholder_url,
            auth_type="public",
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string", "description": "User question about the brand"}},
                "required": ["message"],
            },
            tags=tags,
            trust_verification="verified",
            is_brand_agent=True,
        )
        created_agent = await self.registry_repository.create_agent(agent)

        await self.qdrant_service.upsert_vector(
            point_id=created_agent.id,
            vector=agent_embedding,
            payload={
                "agent_id": agent_id,
                "is_active": True,
                "name": name,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )
        created_agent.qdrant_point_id = created_agent.id
        created_agent.embedding_version = settings.EMBEDDING_VERSION
        await self.registry_repository.update_agent(created_agent)

        return await self.registry_repository.get_agent_by_id(created_agent.id)

    async def get_trending_agents(
        self, window_days: int = 7, limit: int = 20
    ) -> List[Tuple[Agent, int]]:
        """Get agents ordered by invocation count in the last N days."""
        trending_ids = await self.invocation_log_repository.get_trending_agent_ids(
            window_days=window_days, limit=limit
        )
        if not trending_ids:
            return []
        agent_ids = [aid for aid, _ in trending_ids]
        agents = await self.registry_repository.get_agents_by_ids(agent_ids)
        count_by_id = {aid: count for aid, count in trending_ids}
        return [(agent, count_by_id[agent.id]) for agent in agents]
