from pydantic import BaseModel, Field


class ScenarioConfig(BaseModel):
    """Configuration payload to start a simulation scenario."""

    scenario_name: str = Field(..., min_length=1)
    tick_count: int = Field(default=100, gt=0)
    tick_interval_ms: int = Field(
        default=500, ge=50,
        description="Delay between ticks in milliseconds",
    )
    service_agent_count: int = Field(default=5, ge=1)
    buyer_agent_count: int = Field(default=10, ge=1)
    initial_balance: int = Field(default=1000, ge=0)


class ScenarioStatus(BaseModel):
    """Current state of a running or completed scenario."""

    scenario_name: str
    status: str
    current_tick: int
    total_ticks: int
    agents_count: int
    total_trades: int
    total_volume: int


class ScenarioListItem(BaseModel):
    """Available scenario for selection."""

    name: str
    description: str
    default_config: ScenarioConfig
