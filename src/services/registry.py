"""Registry domain service."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.registry import Agent, Capability, AgentRequirement
from src.repositories.registry import RegistryRepository
from src.schemas.registry import AgentManifest, AgentSearchQuery, DiscoverQuery
from src.utilities.embedding import EmbeddingService


class RegistryService:
    """Service for agent registry operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = RegistryRepository(session)
        self.embedding_service = EmbeddingService()

    async def register_agent(self, manifest: AgentManifest, user_id: UUID) -> Agent:
        """Register a new agent."""
        # Check if agent_id already exists
        existing_agent = await self.repository.get_agent_by_agent_id(manifest.agent_id)
        if existing_agent:
            raise ValueError(f"Agent with ID {manifest.agent_id} already exists")

        # Generate embeddings for agent
        agent_text = self.embedding_service.prepare_agent_text_for_embedding(
            manifest.name, manifest.description, manifest.tags
        )
        agent_embedding = await self.embedding_service.generate_embedding(agent_text)

        # Create agent
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
            embedding=agent_embedding,
        )

        # Create capabilities
        capabilities = []
        for cap_data in manifest.capabilities:
            # Generate embedding for capability
            cap_text = self.embedding_service.prepare_capability_text_for_embedding(
                cap_data.id, cap_data.input_schema, cap_data.output_schema
            )
            cap_embedding = await self.embedding_service.generate_embedding(cap_text)

            capability = Capability(
                agent_id=None,  # Will be set after agent is created
                capability_id=cap_data.id,
                input_schema=cap_data.input_schema,
                output_schema=cap_data.output_schema,
                auth_type=cap_data.auth.get("type", "public"),
                embedding=cap_embedding,
            )
            capabilities.append(capability)

        # Create requirements
        requirements = []
        if manifest.requires:
            for req_data in manifest.requires:
                requirement = AgentRequirement(
                    agent_id=None,  # Will be set after agent is created
                    required_capability=req_data["capability"],
                )
                requirements.append(requirement)

        # Save agent first
        created_agent = await self.repository.create_agent(agent)

        # Set agent_id for capabilities and requirements
        for capability in capabilities:
            capability.agent_id = created_agent.id
        for requirement in requirements:
            requirement.agent_id = created_agent.id

        # Add capabilities and requirements to session
        for capability in capabilities:
            self.session.add(capability)
        for requirement in requirements:
            self.session.add(requirement)

        await self.session.commit()

        # Return agent with relationships loaded
        return await self.repository.get_agent_by_id(created_agent.id)

    async def search_agents(self, query: AgentSearchQuery) -> List[Agent]:
        """Search agents with filters."""
        return await self.repository.search_agents(
            tags=query.tags,
            capability=query.capability,
            search_text=query.search,
            limit=query.limit,
            offset=query.offset,
        )

    async def semantic_discover(self, query: DiscoverQuery) -> List[Agent]:
        """Semantic discovery using vector similarity."""
        # Generate embedding for the query
        query_embedding = await self.embedding_service.generate_embedding(query.query)
        
        # Perform semantic search
        return await self.repository.semantic_search(
            embedding=query_embedding,
            limit=query.limit,
        )

    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent_id."""
        return await self.repository.get_agent_by_agent_id(agent_id)

    async def get_agent_by_uuid(self, agent_uuid: UUID) -> Optional[Agent]:
        """Get agent by UUID."""
        return await self.repository.get_agent_by_id(agent_uuid)

    async def update_agent(self, agent_uuid: UUID, manifest: AgentManifest, user_id: UUID) -> Agent:
        """Update an agent (only if owned by user)."""
        agent = await self.repository.get_agent_by_id(agent_uuid)
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

        # Regenerate embeddings
        agent_text = self.embedding_service.prepare_agent_text_for_embedding(
            manifest.name, manifest.description, manifest.tags
        )
        agent.embedding = await self.embedding_service.generate_embedding(agent_text)

        # Update capabilities (delete old ones and create new ones)
        # This is a simplified approach - in production you might want more sophisticated updates
        for capability in agent.capabilities:
            await self.session.delete(capability)
        
        for requirement in agent.requirements:
            await self.session.delete(requirement)

        # Create new capabilities
        for cap_data in manifest.capabilities:
            cap_text = self.embedding_service.prepare_capability_text_for_embedding(
                cap_data.id, cap_data.input_schema, cap_data.output_schema
            )
            cap_embedding = await self.embedding_service.generate_embedding(cap_text)

            capability = Capability(
                agent_id=agent.id,
                capability_id=cap_data.id,
                input_schema=cap_data.input_schema,
                output_schema=cap_data.output_schema,
                auth_type=cap_data.auth.get("type", "public"),
                embedding=cap_embedding,
            )
            self.session.add(capability)

        # Create new requirements
        if manifest.requires:
            for req_data in manifest.requires:
                requirement = AgentRequirement(
                    agent_id=agent.id,
                    required_capability=req_data["capability"],
                )
                self.session.add(requirement)

        return await self.repository.update_agent(agent)

    async def delete_agent(self, agent_uuid: UUID, user_id: UUID) -> bool:
        """Delete an agent (only if owned by user)."""
        agent = await self.repository.get_agent_by_id(agent_uuid)
        if not agent:
            return False
        
        if agent.user_id != user_id:
            raise ValueError("Not authorized to delete this agent")

        return await self.repository.delete_agent(agent_uuid)

    async def get_user_agents(self, user_id: UUID) -> List[Agent]:
        """Get all agents for a user."""
        return await self.repository.get_agents_by_user_id(user_id)