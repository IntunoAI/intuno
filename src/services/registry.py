"""Registry domain service."""

from typing import List, Optional, Tuple
from uuid import UUID

from src.models.registry import Agent, Capability, AgentRequirement
from src.repositories.registry import RegistryRepository
from src.schemas.registry import AgentManifest, AgentSearchQuery, DiscoverQuery
from src.utilities.embedding import EmbeddingService
from src.utilities.qdrant_service import QdrantService
from src.utilities.semantic_enhancement import SemanticEnhancementService
from src.core.settings import settings
from fastapi import Depends


class RegistryService:
    """Service for agent registry operations."""

    def __init__(
        self,
        registry_repository: RegistryRepository = Depends(),
        embedding_service: EmbeddingService = Depends(),
    ):
        self.registry_repository = registry_repository
        self.embedding_service = embedding_service
        self.qdrant_service = QdrantService()
        self.semantic_enhancement = SemanticEnhancementService(
            enabled=settings.ENABLE_LLM_ENHANCEMENT,
            model=settings.LLM_ENHANCEMENT_MODEL,
        )

    async def register_agent(self, manifest: AgentManifest, user_id: UUID, enhance_manifest: bool = True) -> Agent:
        """
        Register a new agent.
        :param manifest: AgentManifest
        :param user_id: UUID
        :param enhance_manifest: Whether to enhance manifest text with LLM
        :return: Agent
        """
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

        # Create agent (without embedding, will store in Qdrant)
        agent = Agent(
            agent_id=manifest.agent_id,
            user_id=user_id,
            name=manifest.name,
            description=manifest.description,
            version=manifest.version,
            invoke_endpoint=manifest.endpoints["invoke"],
            manifest_json=manifest.model_dump(),
            tags=manifest.tags,
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
                auth_type=cap_data.auth_type.get("type", "public"),
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
        Search agents with filters.
        :param query: AgentSearchQuery
        :return: List[Agent]
        """
        return await self.registry_repository.list_agents(
            tags=query.tags,
            capability=query.capability,
            search_text=query.search,
            limit=query.limit,
            offset=query.offset,
        )

    async def semantic_discover(self, query: DiscoverQuery, enhance_query: bool = True) -> List[Tuple[Agent, float]]:
        """
        Semantic discovery using vector similarity.
        :param query: DiscoverQuery
        :param enhance_query: Whether to enhance query with LLM
        :return: List[Tuple[Agent, float]] - List of (agent, similarity_score) tuples
        """
        # Enhance query if enabled
        if enhance_query:
            enhanced_query_text = await self.semantic_enhancement.enhance_discovery_query(query.query)
        else:
            enhanced_query_text = query.query
        
        # Generate embedding for the enhanced query
        query_embedding = await self.embedding_service.generate_embedding(enhanced_query_text, enhance=False)
        
        # Perform semantic search with similarity threshold
        return await self.registry_repository.semantic_discover(
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

    async def update_agent(self, agent_uuid: UUID, manifest: AgentManifest, user_id: UUID, enhance_manifest: bool = True) -> Agent:
        """
        Update an agent (only if owned by user).
        :param agent_uuid: UUID
        :param manifest: AgentManifest
        :param user_id: UUID
        :param enhance_manifest: Whether to enhance manifest text with LLM
        :return: Agent
        """
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            raise ValueError("Agent not found")
        
        if agent.user_id != user_id:
            raise ValueError("Not authorized to update this agent")

        # Update agent fields
        agent.name = manifest.name
        agent.description = manifest.description
        agent.version = manifest.version
        agent.invoke_endpoint = manifest.endpoints["invoke"]
        agent.manifest_json = manifest.model_dump()
        agent.tags = manifest.tags
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
                auth_type=cap_data.auth_type.get("type", "public"),
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

    async def delete_agent(self, agent_uuid: UUID, user_id: UUID) -> bool:
        """
        Delete an agent (only if owned by user).
        :param agent_uuid: UUID
        :param user_id: UUID
        :return: bool
        """
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            return False
        
        if agent.user_id != user_id:
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