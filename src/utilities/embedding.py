"""Embedding service for semantic search — pluggable provider architecture.

Supported providers (set via EMBEDDING_PROVIDER env var):
  - "openai"  — OpenAI text-embedding-3-small (default, requires OPENAI_API_KEY)
  - "ollama"  — Local Ollama server (requires EMBEDDING_URL, no API key needed)
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from src.core.settings import settings
from src.utilities.semantic_enhancement import SemanticEnhancementService

logger = logging.getLogger(__name__)

# Initialize semantic enhancement service (shared across providers)
semantic_enhancement = SemanticEnhancementService(
    enabled=settings.ENABLE_LLM_ENHANCEMENT,
    model=settings.LLM_ENHANCEMENT_MODEL,
)


# ── Provider interface ────────────────────────────────────────────────


class EmbeddingProvider(ABC):
    """Abstract base for embedding backends."""

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """Return a single embedding vector for *text*."""

    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embedding vectors for a list of texts."""

    @property
    @abstractmethod
    def vector_size(self) -> int:
        """Dimensionality of the vectors this provider produces."""


# ── OpenAI provider ──────────────────────────────────────────────────


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings (text-embedding-3-small by default)."""

    # Known dimensions for common models
    _KNOWN_DIMENSIONS: dict[str, int] = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._vector_size = self._KNOWN_DIMENSIONS.get(model, 1536)

    async def generate_embedding(self, text: str) -> List[float]:
        response = await self._client.embeddings.create(model=self._model, input=text)
        return response.data[0].embedding

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [data.embedding for data in response.data]

    @property
    def vector_size(self) -> int:
        return self._vector_size


# ── Ollama provider ──────────────────────────────────────────────────


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama local embeddings (nomic-embed-text, mxbai-embed-large, etc.)."""

    # Common Ollama embedding model dimensions
    _KNOWN_DIMENSIONS: dict[str, int] = {
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
        "snowflake-arctic-embed": 1024,
    }

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._vector_size = self._KNOWN_DIMENSIONS.get(model, 768)

    async def generate_embedding(self, text: str) -> List[float]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": text},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if not embeddings:
                raise ValueError("Ollama returned no embeddings")
            # First call: detect actual vector size
            if len(embeddings[0]) != self._vector_size:
                self._vector_size = len(embeddings[0])
            return embeddings[0]

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings", [])
            if embeddings and len(embeddings[0]) != self._vector_size:
                self._vector_size = len(embeddings[0])
            return embeddings

    @property
    def vector_size(self) -> int:
        return self._vector_size


# ── Provider factory ─────────────────────────────────────────────────


def _create_provider() -> EmbeddingProvider:
    """Instantiate the configured embedding provider."""
    provider_name = settings.EMBEDDING_PROVIDER.lower()
    if provider_name == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.OPENAI_API_KEY,
            model=settings.EMBEDDING_MODEL,
        )
    elif provider_name == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.EMBEDDING_URL,
            model=settings.EMBEDDING_MODEL,
        )
    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER={provider_name!r}. "
            f"Supported: 'openai', 'ollama'"
        )


# Module-level singleton — created on first import
_provider: EmbeddingProvider = _create_provider()


def get_embedding_provider() -> EmbeddingProvider:
    """Return the active embedding provider instance."""
    return _provider


# ── High-level service (preserves existing call-sites) ───────────────


class EmbeddingService:
    """Service for generating embeddings — delegates to the active provider."""

    @staticmethod
    async def generate_embedding(text: str, enhance: bool = True) -> List[float]:
        """Generate embedding for text using the configured provider.

        Results are cached in Redis when EMBEDDING_CACHE_TTL > 0.
        :param text: Text to embed
        :param enhance: Unused (kept for call-site compatibility)
        :return: Embedding vector
        """
        from src.core.redis_client import cache_get, cache_set

        cache_ttl = settings.EMBEDDING_CACHE_TTL
        if cache_ttl > 0:
            cache_key = f"emb:{hashlib.sha256(text.encode()).hexdigest()}"
            cached = await cache_get(cache_key)
            if cached is not None:
                return cached

        try:
            result = await _provider.generate_embedding(text)
        except Exception as e:
            raise Exception(f"Failed to generate embedding: {e}")

        if cache_ttl > 0:
            await cache_set(cache_key, result, ttl_seconds=cache_ttl)
        return result

    @staticmethod
    async def generate_enhanced_embedding(
        agent_name: str,
        description: str,
        tags: List[str],
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> List[float]:
        """Generate enhanced embedding for an agent using LLM text expansion."""
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
            return await _provider.generate_embeddings_batch(texts)
        except Exception as e:
            raise Exception(f"Failed to generate embeddings: {e}")

    @staticmethod
    def prepare_agent_text_for_embedding(
        agent_name: str,
        description: str,
        tags: List[str],
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Prepare agent text for embedding generation."""
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
