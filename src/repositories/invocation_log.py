"""Invocation log repository: persistence for agent invocation logs."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.database import get_db
from src.models.invocation_log import InvocationLog
from src.models.registry import Agent


class InvocationLogRepository:
    """Repository for invocation log operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create_invocation_log(self, invocation_log: InvocationLog) -> InvocationLog:
        """
        Create a new invocation log.
        :param invocation_log: InvocationLog
        :return: InvocationLog
        """
        self.session.add(invocation_log)
        await self.session.commit()
        await self.session.refresh(invocation_log)
        return invocation_log

    async def get_invocation_log_by_id(self, log_id: UUID) -> Optional[InvocationLog]:
        """
        Get invocation log by ID.
        :param log_id: UUID
        :return: Optional[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog).where(InvocationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def get_invocation_logs_by_user_id(
        self, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[InvocationLog]:
        """
        Get invocation logs for a user.
        :param user_id: UUID
        :param limit: int
        :param offset: int
        :return: List[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog)
            .options(selectinload(InvocationLog.target_agent))
            .where(InvocationLog.caller_user_id == user_id)
            .order_by(InvocationLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_invocation_logs_for_dashboard(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
        agent_id: Optional[UUID] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        status: Optional[str] = None,
    ) -> List[InvocationLog]:
        """
        Get invocation logs for dashboard: invocations made BY the user OR targeting the user's agents.
        :param user_id: UUID
        :param limit: int
        :param offset: int
        :param agent_id: Optional filter by target agent
        :param from_date: Optional filter from date (inclusive)
        :param to_date: Optional filter to date (inclusive)
        :param status: Optional filter by status (success, error, timeout)
        :return: List[InvocationLog]
        """
        conditions = [
            or_(
                InvocationLog.caller_user_id == user_id,
                Agent.user_id == user_id,
            )
        ]
        if agent_id is not None:
            conditions.append(InvocationLog.target_agent_id == agent_id)
        if from_date is not None:
            conditions.append(InvocationLog.created_at >= from_date)
        if to_date is not None:
            conditions.append(InvocationLog.created_at <= to_date)
        if status is not None:
            if status == "success":
                conditions.append(InvocationLog.status_code >= 200)
                conditions.append(InvocationLog.status_code < 300)
            elif status == "error":
                conditions.append(
                    and_(
                        or_(
                            InvocationLog.status_code < 200,
                            InvocationLog.status_code >= 300,
                        ),
                        ~InvocationLog.status_code.in_([408, 504]),
                    )
                )
            elif status == "timeout":
                conditions.append(InvocationLog.status_code.in_([408, 504]))
        stmt = (
            select(InvocationLog)
            .options(selectinload(InvocationLog.target_agent))
            .join(Agent, InvocationLog.target_agent_id == Agent.id)
            .where(and_(*conditions))
            .order_by(InvocationLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_invocations_for_dashboard_since(
        self, user_id: UUID, since: datetime
    ) -> int:
        """
        Count invocations for dashboard since a given time.
        Includes invocations made BY the user OR targeting the user's agents.
        """
        result = await self.session.execute(
            select(func.count(InvocationLog.id))
            .select_from(InvocationLog)
            .join(Agent, InvocationLog.target_agent_id == Agent.id)
            .where(
                or_(
                    InvocationLog.caller_user_id == user_id,
                    Agent.user_id == user_id,
                ),
                InvocationLog.created_at >= since,
            )
        )
        return result.scalar() or 0

    async def get_invocation_logs_by_agent_id(
        self, agent_id: UUID, user_id: UUID, limit: int = 50, offset: int = 0
    ) -> List[InvocationLog]:
        """
        Get invocation logs for an agent, scoped to the calling user.
        :param agent_id: UUID
        :param user_id: UUID
        :param limit: int
        :param offset: int
        :return: List[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog)
            .options(selectinload(InvocationLog.target_agent))
            .where(
                InvocationLog.target_agent_id == agent_id,
                InvocationLog.caller_user_id == user_id,
            )
            .order_by(InvocationLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_invocation_logs_by_conversation_id(
        self,
        conversation_id: UUID,
        user_id: UUID,
        limit: int = 50,
    ) -> List[InvocationLog]:
        """
        Get invocation logs for a conversation.
        :param conversation_id: UUID
        :param user_id: UUID
        :param limit: int
        :return: List[InvocationLog]
        """
        result = await self.session.execute(
            select(InvocationLog)
            .where(
                InvocationLog.conversation_id == conversation_id,
                InvocationLog.caller_user_id == user_id,
            )
            .order_by(InvocationLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_invocations_by_user_since(
        self, user_id: UUID, since: datetime
    ) -> int:
        """
        Count invocations by user since a given time.
        :param user_id: UUID
        :param since: datetime
        :return: int
        """
        result = await self.session.execute(
            select(func.count(InvocationLog.id)).where(
                InvocationLog.caller_user_id == user_id,
                InvocationLog.created_at >= since,
            )
        )
        return result.scalar() or 0

    async def get_hourly_aggregates(
        self, user_id: UUID, hours: int = 24
    ) -> List[Tuple[str, float, float]]:
        """
        Get hourly invocation aggregates (hour_label, avg_latency, success_rate) for last N hours.
        Includes invocations made BY the user (caller) OR targeting the user's agents (owner).
        :param user_id: UUID
        :param hours: int (24, 48, or 168)
        :return: List of (hour_label, avg_latency, success_rate)
        """
        if hours not in (24, 48, 168):
            hours = 24
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = text("""
            SELECT date_trunc('hour', il.created_at) AS hour,
                   avg(il.latency_ms) AS avg_latency,
                   sum(CASE WHEN il.status_code >= 200 AND il.status_code < 300 THEN 1 ELSE 0 END) AS successes,
                   count(il.id) AS total
            FROM invocation_logs il
            LEFT JOIN agents a ON a.id = il.target_agent_id
            WHERE (il.caller_user_id = :user_id OR a.user_id = :user_id)
              AND il.created_at >= :since
            GROUP BY date_trunc('hour', il.created_at)
            ORDER BY 1
        """)
        result = await self.session.execute(stmt, {"user_id": user_id, "since": since})
        rows = result.all()
        out: List[Tuple[str, float, float]] = []
        for row in rows:
            total = row.total or 0
            successes = row.successes or 0
            success_rate = (successes / total * 100) if total else 0.0
            avg_lat = float(row.avg_latency) if row.avg_latency else 0.0
            hour_label = row.hour.strftime("%H:00") if row.hour else ""
            out.append((hour_label, avg_lat, round(success_rate, 1)))
        return out

    async def count_invocations_for_integration(
        self,
        integration_id: Optional[UUID],
        since: datetime,
        until: Optional[datetime] = None,
    ) -> int:
        """
        Count invocations for an integration in a time window.
        If integration_id is None, counts global invocations (no integration filter).
        :param integration_id: Optional[UUID]
        :param since: datetime
        :param until: Optional[datetime]
        :return: int
        """
        until = until or datetime.now(timezone.utc)
        q = select(func.count(InvocationLog.id)).where(
            InvocationLog.created_at >= since,
            InvocationLog.created_at <= until,
        )
        if integration_id is not None:
            q = q.where(InvocationLog.integration_id == integration_id)
        result = await self.session.execute(q)
        return result.scalar() or 0

    async def get_agent_quality_metrics(
        self, agent_id: UUID, window_days: int = 90
    ) -> Tuple[Optional[float], Optional[float], int]:
        """
        Get quality metrics for an agent from invocation logs (on-demand).
        :param agent_id: UUID
        :param window_days: int
        :return: Tuple[Optional[float], Optional[float], int]
        """
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        result = await self.session.execute(
            select(
                func.count(InvocationLog.id).label("total"),
                func.sum(case((InvocationLog.status_code == 200, 1), else_=0)).label("successes"),
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
        """
        Get quality metrics for multiple agents (on-demand).
        :param agent_ids: List[UUID]
        :param window_days: int
        :return: Dict[UUID, Tuple[Optional[float], Optional[float], int]]
        """
        if not agent_ids:
            return {}
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        result = await self.session.execute(
            select(
                InvocationLog.target_agent_id,
                func.count(InvocationLog.id).label("total"),
                func.sum(case((InvocationLog.status_code == 200, 1), else_=0)).label("successes"),
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
        """
        Get agent IDs ordered by invocation count in the last N days (for trending).
        :param window_days: int
        :param limit: int
        :return: List[Tuple[UUID, int]]
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

    async def get_analytics_summary(
        self,
        user_id: UUID,
        days: int = 7,
    ) -> tuple[
        int,
        float,
        int,
        float,
        List[Tuple[str, int, int]],
        List[Tuple[str, float, float]],
    ]:
        """
        Get aggregated analytics for a user over the last N days.
        Includes invocations made BY the user OR targeting the user's agents.
        Returns (total, success_rate, failed, avg_latency, by_date, by_agent).
        """
        since = datetime.now(timezone.utc) - timedelta(days=days)
        base_filter = and_(
            or_(
                InvocationLog.caller_user_id == user_id,
                Agent.user_id == user_id,
            ),
            InvocationLog.created_at >= since,
        )

        # Total, failed, success rate, avg latency
        row = (
            await self.session.execute(
                select(
                    func.count(InvocationLog.id).label("total"),
                    func.sum(case((and_(InvocationLog.status_code >= 200, InvocationLog.status_code < 300), 1), else_=0)).label("successes"),
                    func.avg(InvocationLog.latency_ms).label("avg_latency"),
                )
                .select_from(InvocationLog)
                .join(Agent, InvocationLog.target_agent_id == Agent.id)
                .where(base_filter)
            )
        ).one()
        total = row.total or 0
        successes = row.successes or 0
        failed = total - successes
        success_rate = (successes / total * 100) if total else 0.0
        avg_latency = float(row.avg_latency) if row.avg_latency else 0.0

        # By date
        date_stmt = (
            select(
                func.date(InvocationLog.created_at).label("d"),
                func.count(InvocationLog.id).label("count"),
                func.sum(case((and_(InvocationLog.status_code >= 200, InvocationLog.status_code < 300), 0), else_=1)).label("failed"),
            )
            .select_from(InvocationLog)
            .join(Agent, InvocationLog.target_agent_id == Agent.id)
            .where(base_filter)
            .group_by(func.date(InvocationLog.created_at))
            .order_by(func.date(InvocationLog.created_at))
        )
        date_rows = (await self.session.execute(date_stmt)).all()
        by_date = [
            (r.d.strftime("%b %d") if r.d else "", r.count or 0, r.failed or 0)
            for r in date_rows
        ]

        # By agent (target_agent_id) - use agent name for display
        agent_stmt = (
            select(
                Agent.name,
                func.count(InvocationLog.id).label("total"),
                func.sum(case((and_(InvocationLog.status_code >= 200, InvocationLog.status_code < 300), 1), else_=0)).label("successes"),
            )
            .select_from(InvocationLog)
            .join(Agent, InvocationLog.target_agent_id == Agent.id)
            .where(base_filter)
            .group_by(Agent.id, Agent.name)
        )
        agent_rows = (await self.session.execute(agent_stmt)).all()
        by_agent: List[Tuple[str, float, float]] = []
        for r in agent_rows:
            t = r.total or 0
            s = r.successes or 0
            success_pct = (s / t * 100) if t else 0.0
            fail_pct = (100 - success_pct) if t else 0.0
            agent_name = r.name or "Unknown"
            by_agent.append((agent_name, round(success_pct, 1), round(fail_pct, 1)))

        return (total, success_rate, failed, avg_latency, by_date, by_agent)
