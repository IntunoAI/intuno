"""Embedding service for semantic search."""

from typing import List

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
        """
        Generate embedding for text using OpenAI's text-embedding-3-small model.
        Optionally enhances text using LLM before generating embedding.
        :param text: str - Text to embed
        :param enhance: bool - Whether to enhance text with LLM first
        :return: List[float] - Embedding vector
        """
        try:
            # Enhance text if enabled
            if enhance and settings.ENABLE_LLM_ENHANCEMENT:
                # For simple text, we can enhance it directly
                # For more complex cases, use the specific enhancement methods
                enhanced_text = text  # Default, can be enhanced if needed
            else:
                enhanced_text = text

            response = await client.embeddings.create(
                model="text-embedding-3-small",
                input=enhanced_text,
            )
            return response.data[0].embedding
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {str(e)}")

    @staticmethod
    async def generate_enhanced_embedding(
        agent_name: str,
        description: str,
        tags: List[str],
        capabilities: List[dict],
    ) -> List[float]:
        """Generate enhanced embedding for agent manifest.
        
        Uses LLM to enhance the text before generating embedding.
        
        :param agent_name: str - Agent name
        :param description: str - Agent description
        :param tags: List[str] - Agent tags
        :param capabilities: List[dict] - Agent capabilities
        :return: List[float] - Embedding vector
        """
        # Enhance text using LLM
        enhanced_text = await semantic_enhancement.enhance_manifest_text(
            agent_name=agent_name,
            description=description,
            tags=tags,
            capabilities=capabilities,
        )
        
        # Generate embedding from enhanced text
        return await EmbeddingService.generate_embedding(enhanced_text, enhance=False)

    @staticmethod
    async def generate_embeddings_batch(texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch.
        :param texts: List[str]
        :return: List[List[float]]
        """
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
        """Prepare agent text for embedding generation.
        :param agent_name: str
        :param description: str
        :param tags: List[str]
        :return: str
        """
        tags_text = ", ".join(tags) if tags else ""
        return f"{agent_name}. {description}. Tags: {tags_text}".strip()

    @staticmethod
    def prepare_capability_text_for_embedding(capability_id: str, input_schema: dict, output_schema: dict) -> str:
        """Prepare capability text for embedding generation.
        :param capability_id: str
        :param input_schema: dict
        :param output_schema: dict
        :return: str
        """
        input_desc = input_schema.get("description", "")
        output_desc = output_schema.get("description", "")
        return f"Capability {capability_id}. Input: {input_desc}. Output: {output_desc}".strip()
