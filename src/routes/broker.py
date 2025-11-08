"""Broker routes for agent invocations."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import get_current_user
from src.core.security import get_user_from_api_key
from src.models.auth import User
from src.schemas.broker import InvocationLogResponse, InvokeRequest, InvokeResponse
from src.services.broker import BrokerService

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(
    invoke_request: InvokeRequest,
    current_user: User = Depends(get_user_from_api_key),
    broker_service: BrokerService = Depends(),
):
    """
    Invoke an agent capability through the broker.
    :param invoke_request: InvokeRequest
    :param current_user: User
    :param broker_service: BrokerService
    :return: InvokeResponse
    """

    try:
        response = await broker_service.invoke_agent(invoke_request, current_user.id)
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Broker error: {str(e)}",
        )


@router.get("/logs", response_model=List[InvocationLogResponse])
async def get_invocation_logs(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    broker_service: BrokerService = Depends(),
):
    """
    Get invocation logs for the current user.
    :param current_user: User
    :param limit: int
    :param broker_service: BrokerService
    :return: List[InvocationLogResponse]
    """

    logs = await broker_service.get_invocation_logs(current_user.id, limit)

    return [
        InvocationLogResponse(
            id=log.id,
            caller_user_id=log.caller_user_id,
            target_agent_id=log.target_agent_id,
            capability_id=log.capability_id,
            status_code=log.status_code,
            latency_ms=log.latency_ms,
            error_message=log.error_message,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get("/logs/agent/{agent_id}", response_model=List[InvocationLogResponse])
async def get_agent_invocation_logs(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    broker_service: BrokerService = Depends(),
):
    """
    Get invocation logs for a specific agent.
    :param agent_id: UUID
    :param current_user: User
    :param limit: int
    :param broker_service: BrokerService
    :return: List[InvocationLogResponse]
    """

    logs = await broker_service.get_agent_invocation_logs(agent_id, limit)

    return [
        InvocationLogResponse(
            id=log.id,
            caller_user_id=log.caller_user_id,
            target_agent_id=log.target_agent_id,
            capability_id=log.capability_id,
            status_code=log.status_code,
            latency_ms=log.latency_ms,
            error_message=log.error_message,
            created_at=log.created_at,
        )
        for log in logs
    ]
