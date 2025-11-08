"""Pydantic models for the Wisdom SDK."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Capability(BaseModel):
    """Represents an agent's capability."""

    id: str
    name: str
    description: str
    input_schema: Dict[str, Any] = Field(..., alias="inputSchema")
    output_schema: Dict[str, Any] = Field(..., alias="outputSchema")


class Agent(BaseModel):
    """Represents a Wisdom Agent."""

    id: str  # Internal UUID
    agent_id: str = Field(..., alias="agentId")
    name: str
    description: str
    version: str
    tags: List[str]
    is_active: bool = Field(..., alias="isActive")
    capabilities: List[Capability]


class InvokeResult(BaseModel):
    """Represents the result of an agent invocation."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: int = Field(..., alias="latencyMs")
    status_code: int = Field(..., alias="statusCode")
