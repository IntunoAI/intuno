"""Invocation log service: delegates to InvocationLogRepository."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import Depends

from src.models.invocation_log import InvocationLog
from src.repositories.invocation_log import InvocationLogRepository


class InvocationLogService:
    """Service for invocation log operations."""

    def __init__(self, invocation_log_repository: InvocationLogRepository = Depends()):
        self.invocation_log_repository = invocation_log_repository

    async def get_invocation_logs(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
        agent_id: Optional[UUID] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> List[InvocationLog]:
        """Get invocation logs for a user (caller OR owner of target agent)."""
        return await self.invocation_log_repository.get_invocation_logs_for_dashboard(
            user_id,
            limit=limit,
            offset=offset,
            agent_id=agent_id,
            from_date=from_date,
            to_date=to_date,
            status=status,
        )

    async def get_agent_invocation_logs(
        self,
        agent_id: UUID,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[InvocationLog]:
        """Get invocation logs for an agent, scoped to the calling user."""
        return await self.invocation_log_repository.get_invocation_logs_by_agent_id(
            agent_id, user_id, limit, offset
        )

    async def get_logs_for_conversation(
        self,
        conversation_id: UUID,
        user_id: UUID,
        limit: int = 50,
    ) -> List[InvocationLog]:
        """Get invocation logs for a conversation (user-scoped)."""
        return await self.invocation_log_repository.get_invocation_logs_by_conversation_id(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit,
        )
