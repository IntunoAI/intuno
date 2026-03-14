"""Dashboard service: aggregates stats for the overview."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends

from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.integration import IntegrationRepository
from src.repositories.registry import RegistryRepository


class DashboardService:
    """Service for dashboard stats."""

    def __init__(
        self,
        registry_repository: RegistryRepository = Depends(),
        invocation_log_repository: InvocationLogRepository = Depends(),
        integration_repository: IntegrationRepository = Depends(),
    ):
        self.registry_repository = registry_repository
        self.invocation_log_repository = invocation_log_repository
        self.integration_repository = integration_repository

    async def get_stats(self, user_id: UUID, hours: int = 24) -> dict:
        """
        Get dashboard stats for the current user.
        :param user_id: UUID
        :return: dict with stats matching DashboardStatsResponse
        """
        now = datetime.now(timezone.utc)
        one_hour_ago = now - timedelta(hours=1)

        # Count user's registered agents
        my_agents = await self.registry_repository.get_agents_by_user_id(user_id)
        total_agents = len(my_agents)

        # Count integrations (active connections)
        integrations = await self.integration_repository.get_by_user_id(user_id)
        active_connections = len(integrations)

        # Events in last hour (invocations made by user or targeting user's agents)
        events_last_hour = await self.invocation_log_repository.count_invocations_for_dashboard_since(
            user_id, one_hour_ago
        )

        # Uptime: derive from recent success rate; use — when no invocation data
        logs = await self.invocation_log_repository.get_invocation_logs_for_dashboard(
            user_id, limit=100
        )
        if logs:
            successes = sum(1 for log in logs if 200 <= log.status_code < 300)
            rate = (successes / len(logs)) * 100
            uptime = f"{rate:.1f}%"
        else:
            uptime = "—"

        # Performance data: hourly aggregates for last N hours
        hourly = await self.invocation_log_repository.get_hourly_aggregates(user_id, hours=hours)
        performance_data = [
            {"time": h, "latency": round(avg_lat), "success": success_rate}
            for h, avg_lat, success_rate in hourly
        ]
        if not performance_data:
            performance_data = [
                {"time": "00:00", "latency": 0, "success": 0},
                {"time": "12:00", "latency": 0, "success": 0},
                {"time": "24:00", "latency": 0, "success": 0},
            ]

        # Agent status: active / idle / offline (simplified from user's agents)
        active = sum(1 for a in my_agents if a.is_active)
        inactive = total_agents - active
        agent_status_data = [
            {"name": "Active", "value": active, "color": "#22c55e"},
            {"name": "Idle", "value": max(0, inactive - 1), "color": "#eab308"},
            {"name": "Offline", "value": min(1, inactive), "color": "#6b7280"},
        ]
        if total_agents == 0:
            agent_status_data = [
                {"name": "Active", "value": 0, "color": "#22c55e"},
                {"name": "Idle", "value": 0, "color": "#eab308"},
                {"name": "Offline", "value": 0, "color": "#6b7280"},
            ]

        # Connection health: simplified - integrations count; no fake degraded/critical
        connection_health_data = [
            {"name": "Integrations", "value": active_connections, "color": "#37322F"},
        ]

        # Recent activity: last 5 invocation logs (made by user or targeting user's agents)
        recent_logs = await self.invocation_log_repository.get_invocation_logs_for_dashboard(
            user_id, limit=5
        )
        recent_activity = []
        for log in recent_logs:
            created = log.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            delta = now - created
            mins = int(delta.total_seconds() / 60)
            if mins < 60:
                time_ago = f"{mins} minutes ago"
            else:
                hrs = int(mins / 60)
                time_ago = f"{hrs} hour{'s' if hrs != 1 else ''} ago"
            status = "Success" if 200 <= log.status_code < 300 else "Error"
            agent_name = log.target_agent.name if log.target_agent else "Unknown agent"
            agent_id_str = log.target_agent.agent_id if log.target_agent else str(log.target_agent_id)
            recent_activity.append({
                "title": f"{agent_name} invoked",
                "agent_name": agent_name,
                "agent_id": agent_id_str,
                "status": status,
                "time_ago": time_ago,
            })

        return {
            "total_agents": total_agents,
            "active_connections": active_connections,
            "events_last_hour": events_last_hour,
            "uptime": uptime,
            "performance_data": performance_data,
            "agent_status_data": agent_status_data,
            "connection_health_data": connection_health_data,
            "recent_activity": recent_activity,
        }
