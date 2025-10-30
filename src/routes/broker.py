"""Broker routes for agent invocations."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user
from src.database import get_db
from src.models.auth import User
from src.schemas.broker import InvocationLogResponse, InvokeRequest, InvokeResponse
from src.services.broker import BrokerService

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(
    invoke_request: InvokeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Invoke an agent capability through the broker."""
    broker_service = BrokerService(db)
    
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
    db: AsyncSession = Depends(get_db),
):
    """Get invocation logs for the current user."""
    broker_service = BrokerService(db)
    
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
    db: AsyncSession = Depends(get_db),
):
    """Get invocation logs for a specific agent."""
    broker_service = BrokerService(db)
    
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
