"""Task domain schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    """Task creation schema."""

    goal: str
    input: Dict[str, Any] = {}
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    external_user_id: Optional[str] = None


class StepSchema(BaseModel):
    """Step in task response (step_id, status, result?, error?)."""

    step_id: UUID
    status: str  # pending | running | completed | failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskResponse(BaseModel):
    """Task response schema; parse from ORM with model_validate(task)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    integration_id: Optional[UUID] = None
    status: str
    goal: str
    input: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    conversation_id: Optional[UUID] = None
    message_id: Optional[UUID] = None
    external_user_id: Optional[str] = None
    steps: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    """Task list item schema (minimal for future list endpoint)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    integration_id: Optional[UUID] = None
    status: str
    goal: str
    external_user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
