"""Analytics routes: pre-aggregated metrics."""

from fastapi import APIRouter, Depends, Query

from src.core.auth import get_current_user
from src.models.auth import User
from src.schemas.analytics import AnalyticsSummaryResponse
from src.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    current_user: User = Depends(get_current_user),
    days: int = Query(default=7, ge=1, le=90),
    analytics_service: AnalyticsService = Depends(),
) -> AnalyticsSummaryResponse:
    """Get pre-aggregated analytics summary for the current user."""
    data = await analytics_service.get_summary(current_user.id, days)
    return AnalyticsSummaryResponse(**data)
