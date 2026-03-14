"""Analytics service: pre-aggregated metrics."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends

from src.repositories.invocation_log import InvocationLogRepository


class AnalyticsService:
    """Service for analytics aggregation."""

    def __init__(
        self,
        invocation_log_repository: InvocationLogRepository = Depends(),
    ):
        self.invocation_log_repository = invocation_log_repository

    def _format_time_ago(self, created) -> str:
        """Format created_at as 'X minutes ago' etc."""
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - created
        mins = int(delta.total_seconds() / 60)
        if mins < 1:
            return "Just now"
        if mins < 60:
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        hrs = int(mins / 60)
        if hrs < 24:
            return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
        days = int(hrs / 24)
        return f"{days} day{'s' if days != 1 else ''} ago"

    async def get_summary(
        self,
        user_id: UUID,
        days: int = 7,
    ) -> dict:
        """
        Get analytics summary for the user over the last N days.
        """
        (
            total,
            success_rate,
            failed,
            avg_latency,
            by_date,
            by_agent,
        ) = await self.invocation_log_repository.get_analytics_summary(user_id, days)

        # Recent failures (last 5)
        recent_logs = await self.invocation_log_repository.get_invocation_logs_for_dashboard(
            user_id, limit=50
        )
        failed_logs = [l for l in recent_logs if not (200 <= l.status_code < 300)][:5]
        recent_failures = [
            {
                "agent": l.target_agent.name if l.target_agent else str(l.target_agent_id),
                "error": l.error_message or "Unknown error",
                "time": self._format_time_ago(l.created_at),
            }
            for l in failed_logs
        ]

        return {
            "total_invocations": total,
            "success_rate": round(success_rate, 1),
            "failed_calls": failed,
            "average_latency_ms": round(avg_latency, 0),
            "invocations_by_date": [
                {"date": d, "count": c, "failed": f}
                for d, c, f in by_date
            ],
            "agent_performance": [
                {"agent": a, "success": s, "failures": f}
                for a, s, f in by_agent
            ],
            "recent_failures": recent_failures,
        }
