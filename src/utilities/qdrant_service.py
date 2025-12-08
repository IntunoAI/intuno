"""Qdrant service for vector storage and similarity search."""

from typing import List, Optional, Dict, Any
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchParams,
)

from src.core.settings import settings


class QdrantService:
    """Service for managing Qdrant vector database operations."""

    COLLECTION_NAME = "agents"
    VECTOR_SIZE = 1536  # OpenAI text-embedding-3-small dimension

    def __init__(self):
        """Initialize Qdrant client."""
        self.client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
        )
        self._collection_initialized = False

    async def ensure_collection(self) -> None:
        """Ensure the collection exists and is properly configured."""
        if self._collection_initialized:
            return

        collections = await self.client.get_collections()
        collection_names = [col.name for col in collections.collections]

        if self.COLLECTION_NAME not in collection_names:
            await self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )

        self._collection_initialized = True

    async def upsert_vector(
        self,
        point_id: UUID,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Upsert a vector with metadata into Qdrant.
        
        :param point_id: Unique point ID (typically agent UUID)
        :param vector: Embedding vector (1536 dimensions)
        :param payload: Metadata payload (agent_id, is_active, etc.)
        """
        await self.ensure_collection()

        point = PointStruct(
            id=str(point_id),
            vector=vector,
            payload=payload,
        )

        await self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[point],
        )

    async def search_similar(
        self,
        query_vector: List[float],
        limit: int = 10,
        similarity_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors in Qdrant.
        
        :param query_vector: Query embedding vector
        :param limit: Maximum number of results
        :param similarity_threshold: Maximum distance (0.0-2.0 for cosine)
        :param filter_conditions: Optional filter conditions (e.g., {"is_active": True})
        :return: List of results with id, score, and payload
        """
        await self.ensure_collection()

        # Build filter if conditions provided
        qdrant_filter = None
        if filter_conditions:
            conditions = []
            for key, value in filter_conditions.items():
                conditions.append(
                    FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    )
                )
            if conditions:
                qdrant_filter = Filter(must=conditions)

        # Calculate score threshold (Qdrant uses similarity, not distance)
        # Cosine distance: 0.0 = identical, 2.0 = opposite
        # Cosine similarity: 1.0 = identical, -1.0 = opposite
        # Qdrant returns similarity, so we need to convert threshold
        score_threshold = None
        if similarity_threshold is not None:
            # Convert distance threshold to similarity threshold
            # similarity = 1 - (distance / 2)
            score_threshold = 1.0 - (similarity_threshold / 2.0)

        search_params = SearchParams()
        if score_threshold is not None:
            search_params.score_threshold = score_threshold

        results = await self.client.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            search_params=search_params,
        )

        # Convert results to list of dicts
        return [
            {
                "id": UUID(result.id),
                "score": result.score,
                "distance": 2.0 * (1.0 - result.score),  # Convert similarity back to distance
                "payload": result.payload,
            }
            for result in results
        ]

    async def delete_vector(self, point_id: UUID) -> None:
        """Delete a vector from Qdrant.
        
        :param point_id: Point ID to delete
        """
        await self.ensure_collection()
        await self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=[str(point_id)],
        )

    async def get_vector(self, point_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a vector and its payload by point ID.
        
        :param point_id: Point ID to retrieve
        :return: Vector data with payload or None if not found
        """
        await self.ensure_collection()
        
        result = await self.client.retrieve(
            collection_name=self.COLLECTION_NAME,
            ids=[str(point_id)],
            with_payload=True,
            with_vectors=True,
        )
        
        if result and len(result) > 0:
            point = result[0]
            return {
                "id": UUID(point.id),
                "vector": point.vector,
                "payload": point.payload,
            }
        return None

