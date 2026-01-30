"""Invocation log routes: single place for 12-field log response mapping; same URLs under /broker."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.core.auth import get_current_user
from src.models.auth import User
from src.models.invocation_log import InvocationLog
from src.schemas.invocation_log import InvocationLogResponse
from src.services.conversation import ConversationService
from src.services.invocation_log import InvocationLogService


def _log_to_response(log: InvocationLog) -> InvocationLogResponse:
    """Single place for log -> InvocationLogResponse (12-field mapping)."""
    return InvocationLogResponse(
        id=log.id,
        caller_user_id=log.caller_user_id,
        target_agent_id=log.target_agent_id,
        capability_id=log.capability_id,
        status_code=log.status_code,
        latency_ms=log.latency_ms,
        error_message=log.error_message,
        created_at=log.created_at,
        integration_id=log.integration_id,
        conversation_id=log.conversation_id,
        message_id=log.message_id,
        parent_invocation_id=log.parent_invocation_id,
    )


router = APIRouter(prefix="/broker", tags=["InvocationLog"])


@router.get("/logs", response_model=List[InvocationLogResponse])
async def get_invocation_logs(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    invocation_log_service: InvocationLogService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for the current user."""
    logs = await invocation_log_service.get_invocation_logs(current_user.id, limit)
    return [_log_to_response(log) for log in logs]


@router.get("/logs/agent/{agent_id}", response_model=List[InvocationLogResponse])
async def get_agent_invocation_logs(
    agent_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    invocation_log_service: InvocationLogService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for a specific agent."""
    logs = await invocation_log_service.get_agent_invocation_logs(agent_id, limit)
    return [_log_to_response(log) for log in logs]


@router.get("/conversations/{conversation_id}/logs", response_model=List[InvocationLogResponse])
async def get_conversation_logs(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    conversation_service: ConversationService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for a conversation (user-scoped)."""
    logs = await conversation_service.get_logs(conversation_id, current_user.id, limit)
    return [_log_to_response(log) for log in logs]
