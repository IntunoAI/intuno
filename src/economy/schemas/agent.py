"""Economy-specific agent schemas.

These map to wisdom's Agent model, with economy fields (pricing) and
``capabilities`` as an alias for ``tags``.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    """Payload to register a new agent in the economy."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=2000)
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    input_schema: dict | None = None
    pricing_strategy: str = Field(default="fixed")
    base_price: int = Field(default=100, ge=0)
    initial_balance: int = Field(
        default=1000, ge=0,
        description="Starting wallet balance in credits",
    )


class AgentUpdate(BaseModel):
    """Partial update payload for an existing agent."""

    name: str | None = None
    description: str | None = None
    capabilities: list[str] | None = None
    tags: list[str] | None = None
    category: str | None = None
    input_schema: dict | None = None
    pricing_strategy: str | None = None
    base_price: int | None = None
    is_active: bool | None = None


class AgentResponse(BaseModel):
    """Full agent detail response using wisdom's Agent model."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    category: str | None = None
    input_schema: dict | None = None
    pricing_strategy: str | None = None
    base_price: float | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class AgentListResponse(BaseModel):
    """Lightweight agent representation for list endpoints."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    agent_id: str
    name: str
    description: str
    tags: list[str] = Field(default_factory=list)
    pricing_strategy: str | None = None
    base_price: float | None = None
    is_active: bool = True
    created_at: datetime
