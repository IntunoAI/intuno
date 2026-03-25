from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from src.core.auth import get_current_user
from src.models.auth import User
from src.workflow.exceptions import NotFoundException
from src.workflow.models.schemas import CreateWorkflowRequest, WorkflowResponse
from src.workflow.services.workflows import WorkflowService

router = APIRouter()


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: CreateWorkflowRequest,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(),
):
    return await service.create(body)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    name: str | None = Query(default=None),
    owner_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(),
):
    return await service.list(name=name, owner_id=owner_id, limit=limit, offset=offset)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    service: WorkflowService = Depends(),
):
    result = await service.get(workflow_id)
    if result is None:
        raise NotFoundException("Workflow not found")
    return result
