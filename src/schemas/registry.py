"""Registry domain schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class AuthType(str, Enum):
    """Allowed auth_type values for agents."""

    PUBLIC = "public"
    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"


_VALID_AUTH_TYPES = {e.value for e in AuthType}

# Default header/scheme per auth type
_AUTH_DEFAULTS: Dict[str, Dict[str, str]] = {
    AuthType.API_KEY.value: {"header": "X-API-Key", "scheme": ""},
    AuthType.BEARER_TOKEN.value: {"header": "Authorization", "scheme": "Bearer"},
    AuthType.PUBLIC.value: {"header": "X-API-Key", "scheme": ""},
}


def normalize_auth_type(v: Dict[str, Any]) -> Dict[str, str]:
    """Validate auth_type dict and apply defaults for header/scheme."""
    t = str(v.get("type", "public"))
    if t not in _VALID_AUTH_TYPES:
        raise ValueError(
            f"auth_type must be one of {sorted(_VALID_AUTH_TYPES)}, got '{t}'"
        )
    defaults = _AUTH_DEFAULTS.get(t, _AUTH_DEFAULTS[AuthType.PUBLIC.value])
    header = v.get("header") or defaults["header"]
    scheme = v.get("scheme") if "scheme" in v else defaults["scheme"]
    return {"type": t, "header": str(header), "scheme": str(scheme)}


def parse_auth_type_stored(stored: str) -> Dict[str, str]:
    """Parse auth_type from DB: plain string or legacy JSON."""
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
    t = s if s in _VALID_AUTH_TYPES else AuthType.PUBLIC.value
    return normalize_auth_type({"type": t})


class AgentRegistration(BaseModel):
    """Register or update an agent. Only name, description, and endpoint are required."""

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    endpoint: str = Field(..., description="Invoke URL, e.g. https://api.example.com/invoke")
    auth_type: str = Field(default="public", description="public | api_key | bearer_token")
    input_schema: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional JSON Schema describing what the endpoint accepts",
    )
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    brand_id: Optional[UUID] = None
    pricing_strategy: Optional[str] = Field(
        default=None,
        description="Pricing strategy: fixed | dynamic | auction | None (free)",
    )
    base_price: Optional[float] = Field(
        default=None,
        description="Credits per invocation (None = free)",
    )
    pricing_enabled: bool = Field(
        default=False,
        description="Enable credit billing for this agent",
    )

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, v: str) -> str:
        if v not in _VALID_AUTH_TYPES:
            raise ValueError(f"auth_type must be one of {sorted(_VALID_AUTH_TYPES)}, got '{v}'")
        return v


class AgentUpdate(BaseModel):
    """Update an existing agent."""

    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = Field(default=None, min_length=1)
    endpoint: Optional[str] = None
    auth_type: Optional[str] = None
    input_schema: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    category: Optional[str] = None
    brand_id: Optional[UUID] = None
    pricing_strategy: Optional[str] = None
    base_price: Optional[float] = None
    pricing_enabled: Optional[bool] = None

    @field_validator("auth_type")
    @classmethod
    def validate_auth_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_AUTH_TYPES:
            raise ValueError(f"auth_type must be one of {sorted(_VALID_AUTH_TYPES)}, got '{v}'")
        return v


class RateRequest(BaseModel):
    """Request body for submitting a rating."""

    score: int = Field(..., ge=1, le=5, description="Rating score 1-5")
    comment: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent detail response."""

    id: UUID
    agent_id: str
    name: str
    description: str
    version: str = Field(default="1.0.0")
    endpoint: str
    auth_type: str
    input_schema: Optional[Dict[str, Any]] = None
    tags: List[str]
    category: Optional[str] = None
    trust_verification: str
    is_active: bool
    is_brand_agent: bool = Field(default=False)
    has_credentials: bool = Field(default=False)
    pricing_strategy: Optional[str] = Field(default=None)
    base_price: Optional[float] = Field(default=None)
    pricing_enabled: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime
    rating_avg: Optional[float] = Field(default=None)
    rating_count: int = Field(default=0)
    quality_success_rate: Optional[float] = Field(default=None)
    quality_avg_latency_ms: Optional[float] = Field(default=None)
    quality_invocation_count: int = Field(default=0)


class AgentListResponse(BaseModel):
    """Agent list/discover response."""

    id: UUID
    agent_id: str
    name: str
    description: str
    version: str = Field(default="1.0.0")
    endpoint: str
    auth_type: str
    input_schema: Optional[Dict[str, Any]] = None
    tags: List[str]
    category: Optional[str] = None
    trust_verification: str
    is_active: bool
    is_brand_agent: bool = Field(default=False)
    has_credentials: bool = Field(default=False)
    pricing_strategy: Optional[str] = Field(default=None)
    base_price: Optional[float] = Field(default=None)
    pricing_enabled: bool = Field(default=False)
    created_at: datetime
    similarity_score: Optional[float] = Field(
        default=None,
        description="Cosine distance from query (lower = more similar, 0.0-2.0)",
    )
    rating_avg: Optional[float] = Field(default=None)
    rating_count: int = Field(default=0)
    quality_success_rate: Optional[float] = Field(default=None)
    quality_avg_latency_ms: Optional[float] = Field(default=None)
    quality_invocation_count: int = Field(default=0)
    invocation_count: Optional[int] = Field(default=None)


class RatingResponse(BaseModel):
    """Single rating response."""

    id: UUID
    user_id: UUID
    agent_id: UUID
    score: int
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AgentSearchQuery(BaseModel):
    """Agent search/filter query."""

    tags: Optional[List[str]] = None
    search: Optional[str] = None
    category: Optional[str] = None
    sort: str = Field(default="created_at", description="Sort field: created_at, updated_at, name")
    order: str = Field(default="desc", description="Sort order: asc, desc")
    days: Optional[int] = Field(default=None, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DiscoverQuery(BaseModel):
    """Semantic discovery query."""

    query: str
    limit: int = Field(default=10, ge=1, le=50)
    similarity_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Maximum cosine distance (0.0=same, 2.0=opposite). None = no threshold.",
    )
    rank_by: str = Field(
        default="balanced",
        description="similarity_only | balanced | quality_first",
    )


class GenerateAgentRequest(BaseModel):
    """Request body for AI-assisted agent config generation."""

    description: str = Field(..., min_length=1, description="Natural language description of the agent")
    endpoint: Optional[str] = Field(default=None, description="Known invoke URL (placeholder used if omitted)")


class CredentialSetRequest(BaseModel):
    """Request to set per-agent credential."""

    credential_type: str = Field(..., description="api_key or bearer_token")
    value: str = Field(..., min_length=1)
    auth_header: Optional[str] = Field(None, description="Header name, e.g. X-API-Key or Authorization")
    auth_scheme: Optional[str] = Field(None, description="Scheme for header value, e.g. Bearer")

    @field_validator("credential_type")
    @classmethod
    def validate_credential_type(cls, v: str) -> str:
        if v not in ("api_key", "bearer_token"):
            raise ValueError("credential_type must be api_key or bearer_token")
        return v
