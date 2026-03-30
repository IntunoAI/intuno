"""Webhook endpoints — external systems trigger workflow executions via HTTP."""


import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request

from src.workflow.models.schemas import ExecutionResponse, TriggerRequest
from src.workflow.services.executions import ExecutionService

router = APIRouter()


@router.post(
    "/webhooks/{workflow_id}",
    response_model=ExecutionResponse,
    status_code=201,
)
async def webhook_trigger(
    workflow_id: uuid.UUID,
    request: Request,
    service: ExecutionService = Depends(),
):
    """Accept arbitrary JSON from an external caller and trigger the workflow."""
    body: dict[str, Any] = await request.json()
    return await service.trigger(workflow_id, TriggerRequest(trigger_data=body))
