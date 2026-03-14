"""Dashboard stats schemas."""

from typing import List

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    """Dashboard overview stats for the current user."""

    total_agents: int
    active_connections: int
    events_last_hour: int
    uptime: str
    performance_data: List[dict]
    agent_status_data: List[dict]
    connection_health_data: List[dict]
    recent_activity: List[dict]
