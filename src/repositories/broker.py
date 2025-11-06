"""Broker domain repository."""

from typing import List, Optional
from uuid import UUID
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.models.broker import InvocationLog


class BrokerRepository:
    """Repository for broker domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create_invocation_log(self, invocation_log: InvocationLog) -> InvocationLog:
        """Create a new invocation log.
        :param invocation_log: InvocationLog
        :return: InvocationLog
        """
        self.session.add(invocation_log)
        await self.session.commit()
        await self.session.refresh(invocation_log)
        return invocation_log

    async def get_invocation_log_by_id(self, log_id: UUID) -> Optional[InvocationLog]:
        """Get invocation log by ID.
        :param log_id: UUID
        :return: Optional[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog).where(InvocationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_invocation_logs_by_user_id(self, user_id: UUID, limit: int = 50) -> List[InvocationLog]:
        """Get invocation logs for a user.
        :param user_id: UUID
        :param limit: int
        :return: List[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog)
            .where(InvocationLog.caller_user_id == user_id)
            .order_by(InvocationLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_invocation_logs_by_agent_id(self, agent_id: UUID, limit: int = 50) -> List[InvocationLog]:
        """Get invocation logs for an agent.
        :param agent_id: UUID
        :param limit: int
        :return: List[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog)
            .where(InvocationLog.target_agent_id == agent_id)
            .order_by(InvocationLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
