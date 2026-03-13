"""Analytics schemas."""

from typing import List, Optional

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    """Pre-aggregated analytics summary for a time range."""

    total_invocations: int = Field(description="Total invocation count in the period")
    success_rate: float = Field(description="Success rate (0-100)")
    failed_calls: int = Field(description="Number of failed invocations")
    average_latency_ms: float = Field(description="Average latency in milliseconds")
    invocations_by_date: List[dict] = Field(
        default_factory=list,
        description="List of {date, count, failed} per day",
    )
    agent_performance: List[dict] = Field(
        default_factory=list,
        description="List of {agent, success, failures} per agent",
    )
    top_capabilities: List[dict] = Field(
        default_factory=list,
        description="List of {name, count} sorted by count desc",
    )
    recent_failures: List[dict] = Field(
        default_factory=list,
        description="List of {agent, error, time} for recent failed invocations",
    )
