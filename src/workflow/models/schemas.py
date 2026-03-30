"""Pydantic request/response models for the API layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


class CreateWorkflowRequest(BaseModel):
    """Accepts either raw YAML (as a string in `yaml_definition`) or a
    pre-parsed JSON dict in `definition`.  At least one must be provided."""

    name: str
    yaml_definition: str | None = None
    definition: dict[str, Any] | None = None
    owner_id: uuid.UUID | None = None
    triggers: list[dict[str, Any]] | None = None
    recovery: dict[str, Any] | None = None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    owner_id: uuid.UUID | None
    definition: dict[str, Any]
    triggers: list[dict[str, Any]] | None
    recovery: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TriggerRequest(BaseModel):
    trigger_data: dict[str, Any] = Field(default_factory=dict)


class ExecutionResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    trigger_data: dict[str, Any] | None
    context_id: uuid.UUID
    parent_execution_id: uuid.UUID | None = None
    started_at: datetime
    completed_at: datetime | None
    error: str | None

    model_config = {"from_attributes": True}


class ExecutionListResponse(BaseModel):
    items: list[ExecutionResponse]


# ---------------------------------------------------------------------------
# Process table
# ---------------------------------------------------------------------------


class ProcessEntryResponse(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    step_id: str
    type: str
    target_id: str | None
    target_name: str
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    attempt: int
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    tokens_used: int | None
    cost: float | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Context bus
# ---------------------------------------------------------------------------


class ContextSnapshotResponse(BaseModel):
    context_id: uuid.UUID
    entries: dict[str, Any]
