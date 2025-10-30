"""Embedding service for semantic search."""

from typing import List

from openai import AsyncOpenAI

from src.core.settings import settings

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class EmbeddingService:
    """Service for generating embeddings using OpenAI."""

    @staticmethod
    async def generate_embedding(text: str) -> List[float]:
        """Generate embedding for text using OpenAI's text-embedding-3-small model."""
        try:
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {str(e)}")

    @staticmethod
    async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch."""
        try:
            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=texts,
            )
            return [data.embedding for data in response.data]
        except Exception as e:
            raise Exception(f"Failed to generate embeddings: {str(e)}")

    @staticmethod
    def prepare_agent_text_for_embedding(agent_name: str, description: str, tags: List[str]) -> str:
        """Prepare agent text for embedding generation."""
        tags_text = ", ".join(tags) if tags else ""
        return f"{agent_name}. {description}. Tags: {tags_text}".strip()

    @staticmethod
    def prepare_capability_text_for_embedding(capability_id: str, input_schema: dict, output_schema: dict) -> str:
        """Prepare capability text for embedding generation."""
        input_desc = input_schema.get("description", "")
        output_desc = output_schema.get("description", "")
        return f"Capability {capability_id}. Input: {input_desc}. Output: {output_desc}".strip()
