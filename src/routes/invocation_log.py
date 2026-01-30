"""Invocation log routes: URLs under /broker. Conversation logs at GET /conversations/{id}/logs."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.auth import get_current_user
from src.models.auth import User
from src.schemas.invocation_log import InvocationLogResponse
from src.services.invocation_log import InvocationLogService


router = APIRouter(prefix="/broker", tags=["InvocationLog"])


@router.get("/logs", response_model=List[InvocationLogResponse])
async def get_invocation_logs(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    invocation_log_service: InvocationLogService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for the current user."""
    return await invocation_log_service.get_invocation_logs(current_user.id, limit)


@router.get("/logs/agent/{agent_id}", response_model=List[InvocationLogResponse])
async def get_agent_invocation_logs(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    invocation_log_service: InvocationLogService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for a specific agent."""
    return await invocation_log_service.get_agent_invocation_logs(agent_id, limit)
