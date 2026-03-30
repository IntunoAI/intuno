from fastapi import APIRouter, Depends

from src.economy.schemas.scenario import ScenarioConfig, ScenarioListItem, ScenarioStatus
from src.economy.services.scenarios import ScenarioService

router = APIRouter()


def get_scenario_service() -> ScenarioService:
    """Provide a ScenarioService instance (no DB dependency)."""
    return ScenarioService()


@router.get("", response_model=list[ScenarioListItem])
async def list_scenarios(
    scenario_service: ScenarioService = Depends(get_scenario_service),
) -> list[ScenarioListItem]:
    """List all available simulation scenarios."""
    return await scenario_service.list_available()


@router.post("/start", response_model=ScenarioStatus)
async def start_scenario(
    config: ScenarioConfig,
    scenario_service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioStatus:
    """Start a simulation with the given scenario configuration."""
    return await scenario_service.start_scenario(config)


@router.post("/stop", response_model=ScenarioStatus)
async def stop_scenario(
    scenario_service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioStatus:
    """Stop the currently running simulation."""
    return await scenario_service.stop_scenario()


@router.get("/status", response_model=ScenarioStatus)
async def get_scenario_status(
    scenario_service: ScenarioService = Depends(get_scenario_service),
) -> ScenarioStatus:
    """Get the current simulation status."""
    return await scenario_service.get_status()
