from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from src.core.auth import get_current_user
from src.models.auth import User
from src.workflow.exceptions import NotFoundException
from src.workflow.models.schemas import (
    ContextSnapshotResponse,
    ExecutionListResponse,
    ExecutionResponse,
    ProcessEntryResponse,
    TriggerRequest,
)
from src.workflow.services.executions import ExecutionService

router = APIRouter()


@router.post(
    "/workflows/{workflow_id}/run",
    response_model=ExecutionResponse,
    status_code=201,
)
async def run_workflow(
    workflow_id: uuid.UUID,
    body: TriggerRequest,
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(),
):
    return await service.trigger(workflow_id, body)


@router.get("/executions", response_model=ExecutionListResponse)
async def list_executions(
    workflow_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(),
):
    items = await service.list_executions(
        workflow_id=workflow_id, status=status, limit=limit, offset=offset
    )
    return ExecutionListResponse(items=items)


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(),
):
    result = await service.get_status(execution_id)
    if result is None:
        raise NotFoundException("Execution not found")
    return result


@router.post("/executions/{execution_id}/cancel", response_model=ExecutionResponse)
async def cancel_execution(
    execution_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(),
):
    return await service.cancel(execution_id)


@router.get(
    "/executions/{execution_id}/ps",
    response_model=list[ProcessEntryResponse],
)
async def get_process_table(
    execution_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(),
):
    return await service.get_process_table(execution_id)


@router.get(
    "/executions/{execution_id}/context",
    response_model=ContextSnapshotResponse,
)
async def get_context(
    execution_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    service: ExecutionService = Depends(),
):
    result = await service.get_context(execution_id)
    if result is None:
        raise NotFoundException("Execution not found")
    return result
