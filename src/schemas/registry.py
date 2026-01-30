"""Registry domain schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CapabilitySchema(BaseModel):
    """Capability schema matching the Intuno spec."""
    
    id: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    auth_type: Dict[str, str]


class AgentManifest(BaseModel):
    """Agent manifest schema matching the Intuno spec."""

    agent_id: str
    name: str
    description: str
    version: str
    endpoints: Dict[str, str]
    capabilities: List[CapabilitySchema]
    requires: Optional[List[Dict[str, str]]] = None
    tags: List[str] = []
    category: Optional[str] = None
    trust: Dict[str, str] = {"verification": "self-signed"}


class RateRequest(BaseModel):
    """Request body for submitting a rating."""

    score: int = Field(..., ge=1, le=5, description="Rating score 1-5")
    capability_id: Optional[str] = None
    comment: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent response schema."""

    id: UUID
    agent_id: str
    name: str
    description: str
    version: str
    invoke_endpoint: Optional[str] = None
    manifest_json: Dict[str, Any]
    tags: List[str]
    category: Optional[str] = None
    trust_verification: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    capabilities: List[CapabilitySchema]
    requirements: Optional[List[Dict[str, str]]] = None
    rating_avg: Optional[float] = Field(default=None, description="Average user rating (1-5)")
    rating_count: int = Field(default=0, description="Number of ratings")
    quality_success_rate: Optional[float] = Field(default=None, description="Success rate from broker invocations (0-1, last 90 days)")
    quality_avg_latency_ms: Optional[float] = Field(default=None, description="Average latency in ms from broker invocations")
    quality_invocation_count: int = Field(default=0, description="Number of invocations in the quality window")


class AgentListResponse(BaseModel):
    """Agent list response schema."""

    id: UUID
    agent_id: str
    name: str
    description: str
    version: str
    invoke_endpoint: Optional[str] = None
    tags: List[str]
    category: Optional[str] = None
    trust_verification: str
    is_active: bool
    created_at: datetime
    capabilities: List[CapabilitySchema] = []
    similarity_score: Optional[float] = Field(
        default=None,
        description="Similarity score from semantic search (lower is more similar, 0.0-2.0 for cosine distance)",
    )
    rating_avg: Optional[float] = Field(default=None, description="Average user rating (1-5)")
    rating_count: int = Field(default=0, description="Number of ratings")
    quality_success_rate: Optional[float] = Field(default=None, description="Success rate from broker invocations (0-1)")
    quality_avg_latency_ms: Optional[float] = Field(default=None, description="Average latency in ms from broker invocations")
    quality_invocation_count: int = Field(default=0, description="Number of invocations in the quality window")
    invocation_count: Optional[int] = Field(default=None, description="Invocation count in window (e.g. for trending)")


class RatingResponse(BaseModel):
    """Single rating in list response."""

    id: UUID
    user_id: UUID
    agent_id: UUID
    capability_id: Optional[str] = None
    score: int
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AgentSearchQuery(BaseModel):
    """Agent search query schema."""

    tags: Optional[List[str]] = None
    capability: Optional[str] = None
    search: Optional[str] = None
    category: Optional[str] = None
    sort: str = Field(default="created_at", description="Sort field: created_at, updated_at, name")
    order: str = Field(default="desc", description="Sort order: asc, desc")
    days: Optional[int] = Field(default=None, ge=1, le=365, description="Only agents created in the last N days (for 'new' listing)")
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DiscoverQuery(BaseModel):
    """Semantic discovery query schema."""

    query: str
    limit: int = Field(default=10, ge=1, le=50)
    similarity_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Maximum cosine distance (0.0=same, 2.0=opposite). Lower values = more strict matching. None = no threshold (return all results ordered by similarity).",
    )
    rank_by: str = Field(
        default="balanced",
        description="Ranking strategy: similarity_only (current order), balanced (similarity + quality + recency), quality_first (prioritize quality metrics and ratings).",
    )


class AgentCreate(BaseModel):
    """Agent creation schema."""

    manifest: AgentManifest
    brand_id: Optional[UUID] = None


class AgentUpdate(BaseModel):
    """Agent update schema."""

    manifest: AgentManifest
    brand_id: Optional[UUID] = None
