"""A2A agent discovery and import.

Fetches remote Agent Cards from external A2A-compatible services and
registers them as first-class agents in the Intuno registry + Qdrant.
Once imported, A2A agents are discoverable, invocable, and can join
communication networks — exactly like any other agent.
"""

import logging
from typing import Any, Optional
from urllib.parse import urljoin
from uuid import UUID

import httpx
from fastapi import Depends

from src.core.settings import settings
from src.models.registry import Agent
from src.repositories.registry import RegistryRepository
from src.utilities.embedding import EmbeddingService
from src.utilities.qdrant_service import QdrantService

logger = logging.getLogger(__name__)

# Default paths to try when fetching an Agent Card
AGENT_CARD_PATHS = [
    "/.well-known/agent.json",
    "/agent.json",
    "/a2a/agent-card",
]


class A2ADiscoveryService:
    """Discover and import external A2A agents into the Intuno registry."""

    def __init__(
        self,
        registry_repository: RegistryRepository = Depends(),
        embedding_service: EmbeddingService = Depends(),
    ):
        self.registry_repository = registry_repository
        self.embedding_service = embedding_service
        self.qdrant_service = QdrantService()
        self._http_client: Optional[httpx.AsyncClient] = None

    def set_http_client(self, client: httpx.AsyncClient) -> None:
        self._http_client = client

    async def fetch_agent_card(self, base_url: str) -> Optional[dict[str, Any]]:
        """Fetch an A2A Agent Card from a remote URL.

        Tries well-known paths if the URL doesn't point directly to a card.
        """
        client = self._http_client
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=15)

        try:
            # If the URL looks like it already points to a card, try it directly
            if base_url.endswith(".json") or base_url.endswith("/agent-card"):
                card = await self._try_fetch(client, base_url)
                if card:
                    return card

            # Try well-known paths
            normalized = base_url.rstrip("/")
            for path in AGENT_CARD_PATHS:
                url = f"{normalized}{path}"
                card = await self._try_fetch(client, url)
                if card:
                    return card

            return None
        finally:
            if owns_client:
                await client.aclose()

    async def import_agent(
        self,
        base_url: str,
        user_id: UUID,
        card: Optional[dict[str, Any]] = None,
    ) -> Agent:
        """Import an A2A agent as a first-class Intuno agent.

        Fetches the Agent Card (if not provided), extracts metadata,
        creates a registry entry, generates embeddings, and indexes
        in Qdrant. The resulting agent is fully discoverable and invocable.
        """
        if card is None:
            card = await self.fetch_agent_card(base_url)
            if card is None:
                raise ValueError(
                    f"Could not fetch A2A Agent Card from {base_url}"
                )

        name = card.get("name", "Unknown A2A Agent")
        description = card.get("description", "")
        version = card.get("version", "1.0.0")
        agent_url = card.get("url", base_url)

        # Build a rich description from skills for better embedding
        skills = card.get("skills", [])
        skills_text = ""
        if skills:
            skill_descriptions = [
                s.get("description", s.get("name", ""))
                for s in skills
                if isinstance(s, dict)
            ]
            skills_text = " | Skills: " + ", ".join(skill_descriptions)

        full_description = f"{description}{skills_text}"

        # Determine invoke endpoint — A2A tasks are sent via JSON-RPC
        invoke_endpoint = self._resolve_invoke_endpoint(agent_url, card)

        # Determine auth type from the card
        auth_info = card.get("authentication", {})
        schemes = auth_info.get("schemes", [])
        if "bearer" in schemes:
            auth_type = "bearer_token"
        elif "apiKey" in schemes:
            auth_type = "api_key"
        else:
            auth_type = "public"

        # Build tags from skills and capabilities
        tags = ["a2a", "external"]
        for skill in skills:
            if isinstance(skill, dict) and skill.get("name"):
                tags.append(skill["name"].lower().replace(" ", "-"))

        capabilities = card.get("capabilities", {})
        if capabilities.get("streaming"):
            tags.append("streaming")

        # Check for existing import (by invoke_endpoint)
        existing = await self.registry_repository.find_agent_by_endpoint(
            invoke_endpoint
        )
        if existing:
            # Update existing agent with latest card data
            existing.name = name
            existing.description = full_description
            existing.version = version
            existing.tags = tags
            existing.auth_type = auth_type

            # Re-embed and re-index
            agent_embedding = await self._generate_embedding(
                name, full_description, tags
            )
            await self._upsert_qdrant(existing, agent_embedding)
            return await self.registry_repository.update_agent(existing)

        # Generate agent_id
        import re
        from uuid import uuid4

        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")
        short_id = str(uuid4()).replace("-", "")[:8]
        agent_id = f"a2a-{slug}-{short_id}"

        # Build input schema from A2A card if available
        input_schema = self._extract_input_schema(card)

        # Create agent
        agent = Agent(
            agent_id=agent_id,
            user_id=user_id,
            name=name,
            description=full_description,
            version=version,
            invoke_endpoint=invoke_endpoint,
            auth_type=auth_type,
            input_schema=input_schema,
            tags=tags,
            category="a2a",
            trust_verification="a2a-card",
            supports_streaming=capabilities.get("streaming", False),
        )

        created_agent = await self.registry_repository.create_agent(agent)

        # Embed and index in Qdrant
        agent_embedding = await self._generate_embedding(
            name, full_description, tags
        )
        await self._upsert_qdrant(created_agent, agent_embedding)

        return await self.registry_repository.get_agent_by_id(created_agent.id)

    async def import_multiple(
        self,
        urls: list[str],
        user_id: UUID,
    ) -> list[dict[str, Any]]:
        """Import multiple A2A agents. Returns results per URL."""
        results = []
        for url in urls:
            try:
                agent = await self.import_agent(url, user_id)
                results.append({
                    "url": url,
                    "success": True,
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                })
            except Exception as exc:
                logger.warning("Failed to import A2A agent from %s: %s", url, exc)
                results.append({
                    "url": url,
                    "success": False,
                    "error": str(exc),
                })
        return results

    async def refresh_agent(self, agent_uuid: UUID, user_id: UUID) -> Agent:
        """Re-fetch the Agent Card and update the registry entry."""
        agent = await self.registry_repository.get_agent_by_id(agent_uuid)
        if not agent:
            raise ValueError("Agent not found")
        if agent.user_id != user_id:
            raise ValueError("Not authorized to refresh this agent")
        if "a2a" not in (agent.tags or []):
            raise ValueError("Agent is not an A2A import")

        card = await self.fetch_agent_card(agent.invoke_endpoint)
        if card is None:
            raise ValueError(
                f"Could not fetch updated Agent Card from {agent.invoke_endpoint}"
            )

        return await self.import_agent(
            agent.invoke_endpoint, user_id, card=card
        )

    # ── Internal helpers ─────────────────────────────────────────────

    async def _try_fetch(
        self, client: httpx.AsyncClient, url: str
    ) -> Optional[dict[str, Any]]:
        try:
            response = await client.get(
                url,
                headers={"Accept": "application/json"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                # Validate it looks like an Agent Card
                if isinstance(data, dict) and ("name" in data or "skills" in data):
                    return data
        except Exception:
            pass
        return None

    def _resolve_invoke_endpoint(
        self, agent_url: str, card: dict[str, Any]
    ) -> str:
        """Determine the invoke endpoint from the Agent Card.

        A2A agents typically accept tasks at a /tasks/send endpoint
        relative to their base URL.
        """
        # Check if the card specifies an explicit endpoint
        explicit = card.get("invoke_endpoint") or card.get("endpoint")
        if explicit:
            return explicit

        # Default: A2A JSON-RPC endpoint
        base = agent_url.rstrip("/")
        return base

    def _extract_input_schema(
        self, card: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Extract or generate an input schema from the Agent Card."""
        skills = card.get("skills", [])
        if not skills:
            return {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Input message for the agent",
                    }
                },
                "required": ["message"],
            }

        # Build schema from skills
        properties = {
            "message": {
                "type": "string",
                "description": "Input message for the agent",
            },
            "skill": {
                "type": "string",
                "description": "Target skill ID",
                "enum": [
                    s.get("id", s.get("name", ""))
                    for s in skills
                    if isinstance(s, dict)
                ],
            },
        }
        return {
            "type": "object",
            "properties": properties,
            "required": ["message"],
        }

    async def _generate_embedding(
        self,
        name: str,
        description: str,
        tags: list[str],
    ) -> list[float]:
        """Generate embedding for the agent."""
        try:
            return await self.embedding_service.generate_enhanced_embedding(
                agent_name=name,
                description=description,
                tags=tags,
            )
        except Exception:
            # Fall back to basic embedding
            text = self.embedding_service.prepare_agent_text_for_embedding(
                name, description, tags
            )
            return await self.embedding_service.generate_embedding(text)

    async def _upsert_qdrant(
        self, agent: Agent, embedding: list[float]
    ) -> None:
        """Upsert agent embedding into Qdrant."""
        qdrant_point_id = agent.qdrant_point_id or agent.id
        await self.qdrant_service.upsert_vector(
            point_id=qdrant_point_id,
            vector=embedding,
            payload={
                "agent_id": agent.agent_id,
                "is_active": True,
                "name": agent.name,
                "embedding_version": settings.EMBEDDING_VERSION,
            },
        )
        agent.qdrant_point_id = qdrant_point_id
        agent.embedding_version = settings.EMBEDDING_VERSION
        await self.registry_repository.update_agent(agent)
