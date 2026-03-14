"""Invocation log schemas. Response fields match InvocationLog model (Pydantic from_attributes)."""

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field, model_validator


class InvocationLogResponse(BaseModel):
    """Invocation log response schema; parse from ORM with model_validate(log).
    Includes frontend-friendly aliases: agent_id, timestamp, status, input, output, agent_name."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    caller_user_id: UUID
    target_agent_id: UUID
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
    agent_name: Optional[str] = None
    agent_identifier: Optional[str] = None

    @model_validator(mode="wrap")
    @classmethod
    def inject_agent_name(cls, data, handler):
        """Inject agent_name from ORM target_agent when validating from InvocationLog."""
        instance = handler(data)
        if hasattr(data, "target_agent") and data.target_agent is not None:
            object.__setattr__(instance, "agent_name", data.target_agent.name or "Unknown")
            object.__setattr__(instance, "agent_identifier", data.target_agent.agent_id)
        return instance

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
