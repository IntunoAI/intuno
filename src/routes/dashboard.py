"""Dashboard routes: stats for the overview."""

from fastapi import APIRouter, Depends

from src.core.auth import get_current_user
from src.core.redis_client import cache_get, cache_set
from src.core.settings import settings
from src.models.auth import User
from src.schemas.dashboard import DashboardStatsResponse
from src.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    hours: int = 24,
    current_user: User = Depends(get_current_user),
    dashboard_service: DashboardService = Depends(),
) -> DashboardStatsResponse:
    """Get dashboard stats for the current user. Cached for DASHBOARD_CACHE_TTL seconds."""
    if hours not in (24, 48, 168):
        hours = 24

    cache_key = f"dashboard:stats:{current_user.id}:{hours}"
    if settings.DASHBOARD_CACHE_TTL > 0:
        cached = await cache_get(cache_key)
        if cached is not None:
            return DashboardStatsResponse(**cached)

    data = await dashboard_service.get_stats(current_user.id, hours=hours)

    if settings.DASHBOARD_CACHE_TTL > 0:
        await cache_set(cache_key, data, settings.DASHBOARD_CACHE_TTL)

    return DashboardStatsResponse(**data)
