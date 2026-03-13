"""Invocation log schemas. Response fields match InvocationLog model (Pydantic from_attributes)."""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


class InvocationLogResponse(BaseModel):
    """Invocation log response schema; parse from ORM with model_validate(log).
    Includes frontend-friendly aliases: agent_id, timestamp, status, input, output."""

    model_config = ConfigDict(from_attributes=True)

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
    request_payload: Optional[Dict[str, Any]] = None
    response_payload: Optional[Dict[str, Any]] = None

    @computed_field
    @property
    def agent_id(self) -> str:
        return str(self.target_agent_id)

    @computed_field
    @property
    def timestamp(self) -> str:
        return self.created_at.isoformat()

    @computed_field
    @property
    def status(self) -> Literal["success", "error", "timeout"]:
        if 200 <= self.status_code < 300:
            return "success"
        if self.status_code in (408, 504):
            return "timeout"
        return "error"

    @computed_field
    @property
    def input(self) -> Dict[str, Any]:
        return self.request_payload or {}

    @computed_field
    @property
    def output(self) -> Optional[Dict[str, Any]]:
        return self.response_payload
