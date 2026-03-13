"""Registry domain service."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends

from src.core.credential_crypto import encrypt_credential
from src.core.url_validation import validate_invoke_endpoint
from src.repositories.brand import BrandRepository
from src.models.registry import Agent, AgentRating, Capability, AgentRequirement
from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.registry import RegistryRepository
from src.schemas.registry import AgentManifest, AgentSearchQuery, DiscoverQuery, auth_type_to_stored
from src.utilities.embedding import EmbeddingService
from src.utilities.qdrant_service import QdrantService
from src.utilities.semantic_enhancement import SemanticEnhancementService
from src.core.settings import settings


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
        manifest: AgentManifest,
        user_id: UUID,
        enhance_manifest: bool = True,
        brand_id: Optional[UUID] = None,
    ) -> Agent:
        """
        Register a new agent.
        :param manifest: AgentManifest
        :param user_id: UUID
        :param enhance_manifest: Whether to enhance manifest text with LLM
        :param brand_id: Optional brand to publish under; user must own the brand
        :return: Agent
        """
        # If brand_id provided, ensure user owns the brand
        if brand_id is not None:
            brand = await self.brand_repository.get_by_id(brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Brand not found or you are not the owner")

        # Check if agent_id already exists
        existing_agent = await self.registry_repository.get_agent_by_agent_id(manifest.agent_id)
        if existing_agent:
            raise ValueError(f"Agent with ID {manifest.agent_id} already exists")

        # Generate enhanced embedding for agent
        if enhance_manifest:
            agent_embedding = await self.embedding_service.generate_enhanced_embedding(
                agent_name=manifest.name,
                description=manifest.description,
                tags=manifest.tags,
                capabilities=[cap.model_dump() for cap in manifest.capabilities],
            )
        else:
            agent_text = self.embedding_service.prepare_agent_text_for_embedding(
                manifest.name, manifest.description, manifest.tags
            )
            agent_embedding = await self.embedding_service.generate_embedding(agent_text)

        # Validate invoke_endpoint (SSRF protection)
        invoke_url = manifest.endpoints["invoke"]
        allowed = [h.strip() for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",") if h.strip()]
        if not allowed and settings.ENVIRONMENT == "development":
            allowed = ["localhost", "127.0.0.1"]
        validate_invoke_endpoint(invoke_url, allowed_hosts=allowed if allowed else None)

        # Create agent (without embedding, will store in Qdrant)
        agent = Agent(
            agent_id=manifest.agent_id,
            user_id=user_id,
            brand_id=brand_id,
            name=manifest.name,
            description=manifest.description,
            version=manifest.version,
            invoke_endpoint=invoke_url,
            manifest_json=manifest.model_dump(),
            tags=manifest.tags,
            category=manifest.category,
            trust_verification=manifest.trust.get("verification", "self-signed"),
            qdrant_point_id=None,  # Will be set after agent is created
        )

        # Save agent first to get the ID
        created_agent = await self.registry_repository.create_agent(agent)

        # Store embedding in Qdrant with agent metadata
        qdrant_point_id = created_agent.id  # Use agent UUID as Qdrant point ID
        await self.qdrant_service.upsert_vector(
            point_id=qdrant_point_id,
            vector=agent_embedding,
            payload={
                "agent_id": manifest.agent_id,
                "is_active": True,
                "name": manifest.name,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )

        # Update agent with Qdrant point ID and embedding version
        created_agent.qdrant_point_id = qdrant_point_id
        created_agent.embedding_version = settings.EMBEDDING_VERSION
        await self.registry_repository.update_agent(created_agent)

        # Create capabilities and store their embeddings
        capabilities = []
        for cap_data in manifest.capabilities:
            # Generate enhanced embedding for capability
            cap_text = self.embedding_service.prepare_capability_text_for_embedding(
                cap_data.id, cap_data.input_schema, cap_data.output_schema
            )
            cap_embedding = await self.embedding_service.generate_embedding(cap_text, enhance=False)

            # Create capability first to get UUID
            capability = Capability(
                agent_id=created_agent.id,
                capability_id=cap_data.id,
                input_schema=cap_data.input_schema,
                output_schema=cap_data.output_schema,
                auth_type=auth_type_to_stored(cap_data.auth_type),
                qdrant_point_id=None,  # Will be set after creation
                embedding_version=settings.EMBEDDING_VERSION,
            )
            capabilities.append(capability)
        
        # Add capabilities to database first to get their IDs
        if capabilities:
            await self.registry_repository.add_capabilities(capabilities)
            
            # Now store capability embeddings in Qdrant
            for i, cap_data in enumerate(manifest.capabilities):
                capability = capabilities[i]
                cap_text = self.embedding_service.prepare_capability_text_for_embedding(
                    cap_data.id, cap_data.input_schema, cap_data.output_schema
                )
                cap_embedding = await self.embedding_service.generate_embedding(cap_text, enhance=False)
                
                # Store capability embedding in Qdrant
                capability_point_id = capability.id
                await self.qdrant_service.upsert_capability_vector(
                    point_id=capability_point_id,
                    vector=cap_embedding,
                    payload={
                        "agent_id": manifest.agent_id,
                        "agent_uuid": str(created_agent.id),
                        "capability_id": cap_data.id,
                        "agent_name": manifest.name,
                        "is_active": True,
                        "embedding_version": settings.EMBEDDING_VERSION,
                    },
                )
                
                # Update capability with Qdrant point ID
                capability.qdrant_point_id = capability_point_id
                await self.registry_repository.update_capability(capability)

        # Create requirements
        requirements = []
        if manifest.requires:
            for req_data in manifest.requires:
                requirement = AgentRequirement(
                    agent_id=created_agent.id,
                    required_capability=req_data["capability"],
                )
                requirements.append(requirement)

        # Add requirements via repository
        if requirements:
            await self.registry_repository.add_requirements(requirements)

        # Return agent with relationships loaded
        return await self.registry_repository.get_agent_by_id(created_agent.id)

    async def list_agents(self, query: AgentSearchQuery) -> List[Agent]:
        """
        Search agents with filters and optional sort/order/days.
        :param query: AgentSearchQuery
        :return: List[Agent]
        """
        return await self.registry_repository.list_agents(
            tags=query.tags,
            capability=query.capability,
            search_text=query.search,
            category=query.category,
            sort=query.sort,
            order=query.order,
            days=query.days,
            limit=query.limit,
            offset=query.offset,
        )

    async def semantic_discover(self, query: DiscoverQuery, enhance_query: bool = True) -> List[Tuple[Agent, float]]:
        """
        Semantic discovery using vector similarity, optionally re-ranked by quality and recency.
        :param query: DiscoverQuery (includes rank_by: similarity_only | balanced | quality_first)
        :param enhance_query: Whether to enhance query with LLM
        :return: List[Tuple[Agent, float]] - List of (agent, similarity_score) tuples
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

    async def semantic_discover_with_capability(
        self,
        query: DiscoverQuery,
        enhance_query: bool = True,
    ) -> List[Tuple[Agent, str, float]]:
        """
        Semantic discovery at capability level: returns (Agent, capability_id, distance)
        for each match. Used by orchestrator executor to select agent + capability per step.
        :param query: DiscoverQuery (query text, limit, similarity_threshold)
        :param enhance_query: Whether to enhance query with LLM
        :return: List[Tuple[Agent, str, float]] - (Agent, capability_id, distance) ordered by similarity
        """
        if enhance_query:
            enhanced_query_text = await self.semantic_enhancement.enhance_discovery_query(query.query)
        else:
            enhanced_query_text = query.query
        query_embedding = await self.embedding_service.generate_embedding(enhanced_query_text, enhance=False)
        return await self.registry_repository.semantic_discover_with_capability(
            embedding=query_embedding,
            limit=query.limit,
            similarity_threshold=query.similarity_threshold,
        )

    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """
        Get agent by agent_id.
        :param agent_id: str
        :return: Optional[Agent]
        """
        return await self.registry_repository.get_agent_by_agent_id(agent_id)

    async def get_agent_by_uuid(self, agent_uuid: UUID) -> Optional[Agent]:
        """
        Get agent by UUID.
        :param agent_uuid: UUID
        :return: Optional[Agent]
        """
        return await self.registry_repository.get_agent_by_id(agent_uuid)

    async def update_agent(
        self,
        agent_uuid: UUID,
        manifest: AgentManifest,
        user_id: UUID,
        enhance_manifest: bool = True,
        brand_id: Optional[UUID] = None,
    ) -> Agent:
        """
        Update an agent (only if owned by user or brand owner).
        :param agent_uuid: UUID
        :param manifest: AgentManifest
        :param user_id: UUID
        :param enhance_manifest: Whether to enhance manifest text with LLM
        :param brand_id: Optional brand to assign; user must own the brand
        :return: Agent
        """
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            raise ValueError("Agent not found")

        # Authorization: publisher or brand owner
        if agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Not authorized to update this agent")
        elif agent.user_id != user_id:
            raise ValueError("Not authorized to update this agent")

        # If brand_id in request, validate ownership and set (None = leave unchanged)
        if brand_id is not None:
            brand = await self.brand_repository.get_by_id(brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Brand not found or you are not the owner")
            agent.brand_id = brand_id

        # Validate invoke_endpoint (SSRF protection)
        invoke_url = manifest.endpoints["invoke"]
        allowed = [h.strip() for h in settings.INVOKE_ENDPOINT_ALLOWED_HOSTS.split(",") if h.strip()]
        if not allowed and settings.ENVIRONMENT == "development":
            allowed = ["localhost", "127.0.0.1"]
        validate_invoke_endpoint(invoke_url, allowed_hosts=allowed if allowed else None)

        # Update agent fields
        agent.name = manifest.name
        agent.description = manifest.description
        agent.version = manifest.version
        agent.invoke_endpoint = invoke_url
        agent.manifest_json = manifest.model_dump()
        agent.tags = manifest.tags
        agent.category = manifest.category
        agent.trust_verification = manifest.trust.get("verification", "self-signed")

        # Regenerate enhanced embedding
        if enhance_manifest:
            agent_embedding = await self.embedding_service.generate_enhanced_embedding(
                agent_name=manifest.name,
                description=manifest.description,
                tags=manifest.tags,
                capabilities=[cap.model_dump() for cap in manifest.capabilities],
            )
        else:
            agent_text = self.embedding_service.prepare_agent_text_for_embedding(
                manifest.name, manifest.description, manifest.tags
            )
            agent_embedding = await self.embedding_service.generate_embedding(agent_text)

        # Delete old capability vectors from Qdrant before deleting capabilities
        old_capabilities = await self.registry_repository.get_agent_capabilities(agent.id)
        for old_cap in old_capabilities:
            if old_cap.qdrant_point_id:
                try:
                    await self.qdrant_service.delete_capability_vector(old_cap.qdrant_point_id)
                except Exception:
                    pass  # Continue even if deletion fails
        
        # Update capabilities (delete old ones and create new ones)
        await self.registry_repository.delete_agent_capabilities(agent.id)
        await self.registry_repository.delete_agent_requirements(agent.id)

        # Update embedding in Qdrant with version
        qdrant_point_id = agent.qdrant_point_id or agent.id
        await self.qdrant_service.upsert_vector(
            point_id=qdrant_point_id,
            vector=agent_embedding,
            payload={
                "agent_id": manifest.agent_id,
                "is_active": agent.is_active,
                "name": manifest.name,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )
        agent.qdrant_point_id = qdrant_point_id
        agent.embedding_version = settings.EMBEDDING_VERSION

        # Create new capabilities
        new_capabilities = []
        for cap_data in manifest.capabilities:
            capability = Capability(
                agent_id=agent.id,
                capability_id=cap_data.id,
                input_schema=cap_data.input_schema,
                output_schema=cap_data.output_schema,
                auth_type=auth_type_to_stored(cap_data.auth_type),
                qdrant_point_id=None,  # Will be set after creation
                embedding_version=settings.EMBEDDING_VERSION,
            )
            new_capabilities.append(capability)
        
        # Add capabilities to database first
        if new_capabilities:
            await self.registry_repository.add_capabilities(new_capabilities)
            
            # Store capability embeddings in Qdrant
            for i, cap_data in enumerate(manifest.capabilities):
                capability = new_capabilities[i]
                cap_text = self.embedding_service.prepare_capability_text_for_embedding(
                    cap_data.id, cap_data.input_schema, cap_data.output_schema
                )
                cap_embedding = await self.embedding_service.generate_embedding(cap_text, enhance=False)
                
                # Store capability embedding in Qdrant
                capability_point_id = capability.id
                await self.qdrant_service.upsert_capability_vector(
                    point_id=capability_point_id,
                    vector=cap_embedding,
                    payload={
                        "agent_id": manifest.agent_id,
                        "agent_uuid": str(agent.id),
                        "capability_id": cap_data.id,
                        "agent_name": manifest.name,
                        "is_active": agent.is_active,
                        "embedding_version": settings.EMBEDDING_VERSION,
                    },
                )
                
                # Update capability with Qdrant point ID
                capability.qdrant_point_id = capability_point_id
                await self.registry_repository.update_capability(capability)

        # Create new requirements
        new_requirements = []
        if manifest.requires:
            for req_data in manifest.requires:
                requirement = AgentRequirement(
                    agent_id=agent.id,
                    required_capability=req_data["capability"],
                )
                new_requirements.append(requirement)

        # Add new requirements via repository
        if new_requirements:
            await self.registry_repository.add_requirements(new_requirements)

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
        """
        Set or update per-agent credential (owner or brand owner only).
        :param agent_uuid: UUID
        :param user_id: UUID
        :param credential_type: str (api_key | bearer_token)
        :param value: str (plaintext; will be encrypted at rest)
        :param auth_header: Optional header name (e.g. X-API-Key)
        :param auth_scheme: Optional scheme (e.g. Bearer for Authorization)
        """
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
        """
        Delete all credentials for an agent (owner or brand owner only).
        :param agent_uuid: UUID
        :param user_id: UUID
        :return: int number deleted
        """
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
        """
        Delete an agent (only if owned by user or brand owner).
        :param agent_uuid: UUID
        :param user_id: UUID
        :return: bool
        """
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            return False

        if agent.brand_id:
            brand = await self.brand_repository.get_by_id(agent.brand_id)
            if not brand or brand.owner_id != user_id:
                raise ValueError("Not authorized to delete this agent")
        elif agent.user_id != user_id:
            raise ValueError("Not authorized to delete this agent")

        # Delete capability vectors from Qdrant first
        capabilities = await self.registry_repository.get_agent_capabilities(agent_uuid)
        for cap in capabilities:
            if cap.qdrant_point_id:
                try:
                    await self.qdrant_service.delete_capability_vector(cap.qdrant_point_id)
                except Exception:
                    pass  # Continue even if deletion fails
        
        # Delete from Qdrant if point ID exists
        if agent.qdrant_point_id:
            try:
                await self.qdrant_service.delete_vector(agent.qdrant_point_id)
            except Exception:
                # Continue with deletion even if Qdrant deletion fails
                pass

        return await self.registry_repository.delete_agent(agent_uuid)

    async def get_agents_by_user_id(self, user_id: UUID) -> List[Agent]:
        """
        Get all agents for a user.
        :param user_id: UUID
        :return: List[Agent]
        """
        return await self.registry_repository.get_agents_by_user_id(user_id)

    async def rate_agent(
        self,
        agent_id: str,
        user_id: UUID,
        score: int,
        capability_id: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> AgentRating:
        """
        Submit or update a user's rating for an agent (or capability).
        :param agent_id: str (agent_id string, e.g. agent:ns:name:version)
        :param user_id: UUID
        :param score: int 1-5
        :param capability_id: Optional[str]
        :param comment: Optional[str]
        :return: AgentRating
        """
        agent = await self.registry_repository.get_agent_by_agent_id(agent_id)
        if not agent:
            raise ValueError("Agent not found")
        return await self.registry_repository.upsert_rating(
            user_id=user_id,
            agent_uuid=agent.id,
            score=score,
            capability_id=capability_id,
            comment=comment,
        )

    async def get_rating_aggregate(self, agent_uuid: UUID) -> Tuple[Optional[float], int]:
        """
        Get average rating and count for an agent.
        :param agent_uuid: UUID (agents.id)
        :return: (rating_avg or None, rating_count)
        """
        return await self.registry_repository.get_rating_aggregate(agent_uuid)

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
        return await self.registry_repository.get_ratings_for_agent(
            agent_uuid, limit=limit, offset=offset
        )

    async def get_rating_aggregates_bulk(
        self, agent_uuids: List[UUID]
    ) -> dict:
        """
        Get (rating_avg, rating_count) for multiple agents.
        :param agent_uuids: List[UUID]
        :return: Dict[UUID, Tuple[Optional[float], int]]
        """
        return await self.registry_repository.get_rating_aggregates_bulk(agent_uuids)

    async def get_agent_quality_metrics(
        self, agent_uuid: UUID, window_days: int = 90
    ) -> Tuple[Optional[float], Optional[float], int]:
        """
        Get quality metrics for an agent from invocation logs (on-demand).
        :param agent_uuid: UUID (agents.id)
        :param window_days: int - Only consider last N days
        :return: (success_rate, avg_latency_ms, invocation_count)
        """
        return await self.invocation_log_repository.get_agent_quality_metrics(
            agent_uuid, window_days=window_days
        )

    async def get_agent_quality_metrics_bulk(
        self, agent_uuids: List[UUID], window_days: int = 90
    ) -> Dict[UUID, Tuple[Optional[float], Optional[float], int]]:
        """
        Get quality metrics for multiple agents (on-demand).
        :param agent_uuids: List[UUID]
        :param window_days: int
        :return: Dict[UUID, (success_rate, avg_latency_ms, invocation_count)]
        """
        return await self.invocation_log_repository.get_agent_quality_metrics_bulk(
            agent_uuids, window_days=window_days
        )

    async def create_brand_agent(self, brand: "Brand") -> Optional[Agent]:
        """
        Create the default brand agent when a brand is verified. Idempotent.
        :param brand: Brand ORM (must be verified)
        :return: Agent or None if already exists
        """
        agent_id = f"agent:brand:{brand.slug}:1.0.0"
        existing = await self.registry_repository.get_agent_by_agent_id(agent_id)
        if existing:
            return existing

        placeholder_url = settings.BRAND_AGENT_PLACEHOLDER_URL
        ask_input = {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "User question about the brand"}},
            "required": ["message"],
        }
        ask_output = {
            "type": "object",
            "properties": {"message": {"type": "string", "description": "Response from the brand"}},
        }
        manifest_json = {
            "agent_id": agent_id,
            "name": f"{brand.name} – Official",
            "description": brand.description or f"Official assistant for {brand.name}. Ask about the company, products, or contact.",
            "version": "1.0.0",
            "endpoints": {"invoke": placeholder_url},
            "capabilities": [
                {
                    "id": "ask",
                    "input_schema": ask_input,
                    "output_schema": ask_output,
                    "auth_type": {"type": "public"},
                }
            ],
            "tags": ["brand", brand.slug, "company", "contact"],
            "trust": {"verification": "verified"},
        }
        tags = ["brand", brand.slug, "company", "contact"]

        agent_text = self.embedding_service.prepare_agent_text_for_embedding(
            manifest_json["name"], manifest_json["description"], tags
        )
        agent_embedding = await self.embedding_service.generate_embedding(agent_text, enhance=False)

        agent = Agent(
            agent_id=agent_id,
            user_id=brand.owner_id,
            brand_id=brand.id,
            name=manifest_json["name"],
            description=manifest_json["description"],
            version="1.0.0",
            invoke_endpoint=placeholder_url,
            manifest_json=manifest_json,
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
                "name": manifest_json["name"],
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )
        created_agent.qdrant_point_id = created_agent.id
        created_agent.embedding_version = settings.EMBEDDING_VERSION
        await self.registry_repository.update_agent(created_agent)

        cap = Capability(
            agent_id=created_agent.id,
            capability_id="ask",
            input_schema=ask_input,
            output_schema=ask_output,
            auth_type=auth_type_to_stored({"type": "public"}),
        )
        await self.registry_repository.add_capabilities([cap])
        cap_obj = (await self.registry_repository.get_agent_capabilities(created_agent.id))[0]
        cap_text = self.embedding_service.prepare_capability_text_for_embedding(
            "ask", ask_input, ask_output
        )
        cap_embedding = await self.embedding_service.generate_embedding(cap_text, enhance=False)
        await self.qdrant_service.upsert_capability_vector(
            point_id=cap_obj.id,
            vector=cap_embedding,
            payload={
                "agent_id": agent_id,
                "agent_uuid": str(created_agent.id),
                "capability_id": "ask",
                "agent_name": manifest_json["name"],
                "is_active": True,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )
        cap_obj.qdrant_point_id = cap_obj.id
        await self.registry_repository.update_capability(cap_obj)

        return await self.registry_repository.get_agent_by_id(created_agent.id)

    async def get_trending_agents(
        self, window_days: int = 7, limit: int = 20
    ) -> List[Tuple[Agent, int]]:
        """
        Get agents ordered by invocation count in the last N days (trending).
        :param window_days: int
        :param limit: int
        :return: List[(Agent, invocation_count)] ordered by count desc
        """
        trending_ids = await self.invocation_log_repository.get_trending_agent_ids(
            window_days=window_days, limit=limit
        )
        if not trending_ids:
            return []
        agent_ids = [aid for aid, _ in trending_ids]
        agents = await self.registry_repository.get_agents_by_ids(agent_ids)
        count_by_id = {aid: count for aid, count in trending_ids}
        return [(agent, count_by_id[agent.id]) for agent in agents]