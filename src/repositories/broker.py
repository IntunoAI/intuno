"""Broker domain repository."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy import case, func, select
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

    async def get_agent_quality_metrics(
        self, agent_id: UUID, window_days: int = 90
    ) -> Tuple[Optional[float], Optional[float], int]:
        """Aggregate quality metrics for an agent from invocation logs (on-demand).
        :param agent_id: UUID (agents.id)
        :param window_days: int - Only consider logs from the last N days
        :return: (success_rate 0-1 or None, avg_latency_ms or None, invocation_count)
        """
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        result = await self.session.execute(
            select(
                func.count(InvocationLog.id).label("total"),
                func.sum(case([(InvocationLog.status_code == 200, 1)], else_=0)).label("successes"),
                func.avg(InvocationLog.latency_ms).label("avg_latency"),
            ).where(
                InvocationLog.target_agent_id == agent_id,
                InvocationLog.created_at >= since,
            )
        )
        row = result.one()
        total = row.total or 0
        if total == 0:
            return (None, None, 0)
        successes = row.successes or 0
        success_rate = successes / total
        avg_latency = float(row.avg_latency) if row.avg_latency is not None else None
        return (success_rate, avg_latency, total)

    async def get_agent_quality_metrics_bulk(
        self, agent_ids: List[UUID], window_days: int = 90
    ) -> Dict[UUID, Tuple[Optional[float], Optional[float], int]]:
        """Get quality metrics for multiple agents (on-demand).
        :param agent_ids: List[UUID]
        :param window_days: int
        :return: Dict[agent_id -> (success_rate, avg_latency_ms, invocation_count)]
        """
        if not agent_ids:
            return {}
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        result = await self.session.execute(
            select(
                InvocationLog.target_agent_id,
                func.count(InvocationLog.id).label("total"),
                func.sum(case([(InvocationLog.status_code == 200, 1)], else_=0)).label("successes"),
                func.avg(InvocationLog.latency_ms).label("avg_latency"),
            )
            .where(
                InvocationLog.target_agent_id.in_(agent_ids),
                InvocationLog.created_at >= since,
            )
            .group_by(InvocationLog.target_agent_id)
        )
        rows = result.all()
        out: Dict[UUID, Tuple[Optional[float], Optional[float], int]] = {
            aid: (None, None, 0) for aid in agent_ids
        }
        for row in rows:
            total = row.total or 0
            successes = row.successes or 0
            success_rate = (successes / total) if total else None
            avg_latency = float(row.avg_latency) if row.avg_latency is not None else None
            out[row.target_agent_id] = (success_rate, avg_latency, total)
        return out

    async def get_trending_agent_ids(
        self, window_days: int = 7, limit: int = 20
    ) -> List[Tuple[UUID, int]]:
        """Get agent IDs ordered by invocation count in the last N days (for trending).
        :param window_days: int
        :param limit: int
        :return: List[(agent_id, invocation_count)] ordered by count desc
        """
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        result = await self.session.execute(
            select(
                InvocationLog.target_agent_id,
                func.count(InvocationLog.id).label("invocation_count"),
            )
            .where(InvocationLog.created_at >= since)
            .group_by(InvocationLog.target_agent_id)
            .order_by(func.count(InvocationLog.id).desc())
            .limit(limit)
        )
        return [(row.target_agent_id, row.invocation_count) for row in result.all()]
