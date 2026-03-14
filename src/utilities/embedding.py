"""Embedding service for semantic search."""

from typing import Dict, Any, List, Optional

from openai import AsyncOpenAI

from src.core.settings import settings
from src.utilities.semantic_enhancement import SemanticEnhancementService

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# Initialize semantic enhancement service
semantic_enhancement = SemanticEnhancementService(
    enabled=settings.ENABLE_LLM_ENHANCEMENT,
    model=settings.LLM_ENHANCEMENT_MODEL,
)


class EmbeddingService:
    """Service for generating embeddings using OpenAI."""

    @staticmethod
    async def generate_embedding(text: str, enhance: bool = True) -> List[float]:
        """Generate embedding for text using OpenAI's text-embedding-3-small model.
        :param text: Text to embed
        :param enhance: Unused (kept for call-site compatibility)
        :return: Embedding vector
        """
        try:
            response = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {str(e)}")

    @staticmethod
    async def generate_enhanced_embedding(
        agent_name: str,
        description: str,
        tags: List[str],
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> List[float]:
        """Generate enhanced embedding for an agent using LLM text expansion.

        :param agent_name: Agent name
        :param description: Agent description
        :param tags: Agent tags
        :param input_schema: Optional input schema for richer embedding
        :return: Embedding vector
        """
        enhanced_text = await semantic_enhancement.enhance_agent_text(
            agent_name=agent_name,
            description=description,
            tags=tags,
            input_schema=input_schema,
        )
        return await EmbeddingService.generate_embedding(enhanced_text, enhance=False)

    @staticmethod
    async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch."""
        try:
            response = await client.embeddings.create(
                model=settings.EMBEDDING_MODEL,
                input=texts,
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            raise Exception(f"Failed to generate embeddings: {str(e)}")

    @staticmethod
    def prepare_agent_text_for_embedding(
        agent_name: str,
        description: str,
        tags: List[str],
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Prepare agent text for embedding generation.

        Includes name, description, tags, and optional input schema field descriptions.
        """
        parts = [f"{agent_name}.", description]
        if tags:
            parts.append(f"Tags: {', '.join(tags)}")
        if input_schema and input_schema.get("properties"):
            prop_descs = []
            for prop_name, prop_schema in input_schema["properties"].items():
                prop_type = prop_schema.get("type", "")
                prop_desc = prop_schema.get("description", "")
                label = prop_desc or prop_type or prop_name
                prop_descs.append(f"{prop_name}: {label}")
            if prop_descs:
                parts.append(f"Accepts: {', '.join(prop_descs)}")
        return " ".join(parts).strip()
