"""Invocation log routes: URLs under /broker. Conversation logs at GET /conversations/{id}/logs."""

from datetime import datetime
from typing import List, Optional
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
    offset: int = Query(default=0, ge=0),
    agent_id: Optional[UUID] = Query(default=None, description="Filter by target agent ID"),
    from_date: Optional[str] = Query(default=None, description="Filter from date (ISO 8601)"),
    to_date: Optional[str] = Query(default=None, description="Filter to date (ISO 8601)"),
    status: Optional[str] = Query(
        default=None, description="Filter by status: success, error, timeout"
    ),
    invocation_log_service: InvocationLogService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for the current user (caller OR owner of target agent)."""
    from_dt: Optional[datetime] = None
    to_dt: Optional[datetime] = None
    if from_date:
        try:
            from_dt = datetime.fromisoformat(from_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    if to_date:
        try:
            to_dt = datetime.fromisoformat(to_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    return await invocation_log_service.get_invocation_logs(
        current_user.id,
        limit=limit,
        offset=offset,
        agent_id=agent_id,
        from_date=from_dt,
        to_date=to_dt,
        status=status,
    )


@router.get("/logs/agent/{agent_id}", response_model=List[InvocationLogResponse])
async def get_agent_invocation_logs(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    invocation_log_service: InvocationLogService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for a specific agent (scoped to calling user).
    :param agent_id: UUID
    :param current_user: User
    :param limit: int
    :param offset: int
    :param invocation_log_service: InvocationLogService
    :return: List[InvocationLogResponse]
    """
    return await invocation_log_service.get_agent_invocation_logs(
        agent_id, current_user.id, limit, offset
    )
