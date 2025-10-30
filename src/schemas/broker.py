"""Broker domain schemas."""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class InvokeRequest(BaseModel):
    """Agent invocation request schema."""
    
    agent_id: str
    capability_id: str
    input: Dict[str, Any]


class InvokeResponse(BaseModel):
    """Agent invocation response schema."""
    
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: int
    status_code: int


class InvocationLogResponse(BaseModel):
    """Invocation log response schema."""
    
    id: UUID
    caller_user_id: UUID
    target_agent_id: UUID
    capability_id: str
    status_code: int
    latency_ms: int
    error_message: Optional[str] = None
    created_at: datetime