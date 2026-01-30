"""Invocation log schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class InvocationLogResponse(BaseModel):
    """Invocation log response schema (12-field mapping)."""

    id: UUID
    caller_user_id: UUID
    target_agent_id: UUID
    capability_id: str
    status_code: int
    latency_ms: int
    error_message: Optional[str] = None
    created_at: datetime
    integration_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    parent_invocation_id: Optional[UUID] = None
