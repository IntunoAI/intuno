"""Broker domain schemas: invoke request/response; config for API (optional)."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel


class InvokeRequest(BaseModel):
    """Agent invocation request schema."""

    agent_id: str
    capability_id: str
    input: Dict[str, Any]
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    external_user_id: Optional[str] = None


class InvokeResponse(BaseModel):
    """Agent invocation response schema."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    latency_ms: int
    status_code: int
    conversation_id: Optional[UUID] = None


class BrokerConfigResponse(BaseModel):
    """Broker config response (for GET /broker/config or integration broker-config)."""

    id: UUID
    integration_id: Optional[UUID] = None
    request_timeout_seconds: int
    max_retries: Optional[int] = None
    retry_backoff_seconds: Optional[int] = None
    monthly_invocation_quota: Optional[int] = None
    daily_invocation_quota: Optional[int] = None
    allowed_agent_ids: Optional[List[UUID]] = None


class BrokerConfigUpdate(BaseModel):
    """Broker config update (for PATCH)."""

    request_timeout_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    retry_backoff_seconds: Optional[int] = None
    monthly_invocation_quota: Optional[int] = None
    daily_invocation_quota: Optional[int] = None
    allowed_agent_ids: Optional[List[UUID]] = None