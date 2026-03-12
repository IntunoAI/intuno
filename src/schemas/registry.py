"""Registry domain schemas. Response classes know how to parse ORM (CapabilitySchema.from_capability)."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.models.registry import AgentRequirement, Capability


class AuthType(str, Enum):
    """Allowed auth_type values for capabilities. oauth2 deferred."""

    PUBLIC = "public"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"


_VALID_AUTH_TYPES = {e.value for e in AuthType}

# Default header/scheme per auth type (users can override via manifest)
_AUTH_DEFAULTS: Dict[str, Dict[str, str]] = {
    AuthType.API_KEY.value: {"header": "X-API-Key", "scheme": ""},
    AuthType.BEARER_TOKEN.value: {"header": "Authorization", "scheme": "Bearer"},
    AuthType.PUBLIC.value: {"header": "X-API-Key", "scheme": ""},  # when credential sent for public
}


def auth_type_to_stored(auth_type: Dict[str, str]) -> str:
    """Serialize auth_type dict to JSON string for DB storage."""
    import json
    return json.dumps(
        {"type": auth_type.get("type", "public"), "header": auth_type.get("header", ""), "scheme": auth_type.get("scheme", "")}
    )


def normalize_auth_type(v: Dict[str, Any]) -> Dict[str, str]:
    """Validate auth_type and apply defaults for header/scheme. Returns normalized dict."""
    t = str(v.get("type", "public"))
    if t not in _VALID_AUTH_TYPES:
        raise ValueError(
            f"auth_type must be one of {sorted(_VALID_AUTH_TYPES)}, got '{t}'"
        )
    defaults = _AUTH_DEFAULTS.get(t, _AUTH_DEFAULTS[AuthType.PUBLIC.value])
    header = v.get("header") or defaults["header"]
    scheme = v.get("scheme") if "scheme" in v else defaults["scheme"]
    return {"type": t, "header": str(header), "scheme": str(scheme)}


class CapabilitySchema(BaseModel):
    """Capability schema matching the Intuno spec. Model has capability_id and auth_type str."""

    id: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    auth_type: Dict[str, str]

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Ensure auth_type['type'] is one of public, api_key, bearer_token. Allow optional header/scheme."""
        return normalize_auth_type(v)

    @classmethod
    def from_capability(cls, cap: Capability) -> "CapabilitySchema":
        """Build from ORM Capability (id ← capability_id, auth_type parsed from JSON or legacy string)."""
        auth_config = parse_auth_type_stored(cap.auth_type)
        return cls(
            id=cap.capability_id,
            input_schema=cap.input_schema,
            output_schema=cap.output_schema,
            auth_type=auth_config,
        )


def parse_auth_type_stored(stored: str) -> Dict[str, str]:
    """Parse auth_type from DB: JSON or legacy plain string."""
    import json

    if not stored:
        return normalize_auth_type({"type": "public"})
    s = stored.strip()
    if s.startswith("{"):
        try:
            parsed = json.loads(s)
            data: Dict[str, str] = {"type": parsed.get("type", "public")}
            if parsed.get("header"):
                data["header"] = parsed["header"]
            if "scheme" in parsed:
                data["scheme"] = parsed["scheme"]
            return normalize_auth_type(data)
        except json.JSONDecodeError:
            pass
    # Legacy: plain type string
    t = s if s in _VALID_AUTH_TYPES else AuthType.PUBLIC.value
    return normalize_auth_type({"type": t})


def requirements_from_orm(requirements: List[AgentRequirement]) -> List[Dict[str, str]]:
    """Build requirements list for AgentResponse from ORM AgentRequirement list."""
    return [{"capability": req.required_capability} for req in requirements]


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


class CredentialSetRequest(BaseModel):
    """Request to set per-agent credential."""

    credential_type: str = Field(..., description="api_key or bearer_token")
    value: str = Field(..., min_length=1)
    auth_header: Optional[str] = Field(None, description="Header name, e.g. X-API-Key or Authorization")
    auth_scheme: Optional[str] = Field(None, description="Scheme for header value, e.g. Bearer (for Authorization)")

    @field_validator("credential_type")
    @classmethod
    def validate_credential_type(cls, v: str) -> str:
        if v not in ("api_key", "bearer_token"):
            raise ValueError("credential_type must be api_key or bearer_token")
        return v
