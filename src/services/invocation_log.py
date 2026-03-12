"""Invocation log service: delegates to InvocationLogRepository."""

from typing import List
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
    ) -> List[InvocationLog]:
        """Get invocation logs for a user."""
        return await self.invocation_log_repository.get_invocation_logs_by_user_id(
            user_id, limit
        )

    async def get_agent_invocation_logs(
        self,
        agent_id: UUID,
        user_id: UUID,
        limit: int = 50,
    ) -> List[InvocationLog]:
        """Get invocation logs for an agent, scoped to the calling user."""
        return await self.invocation_log_repository.get_invocation_logs_by_agent_id(
            agent_id, user_id, limit
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
