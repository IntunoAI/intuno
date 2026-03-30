from fastapi import HTTPException

from src.economy.schemas.scenario import ScenarioConfig, ScenarioListItem, ScenarioStatus
from src.economy.utilities.scenarios import get_scenario, list_scenarios
from src.economy.utilities.simulator import simulator


class ScenarioService:
    """Manages simulation lifecycle: listing, starting, stopping, and status."""

    async def list_available(self) -> list[ScenarioListItem]:
        """Return all available scenario definitions."""
        raw = list_scenarios()
        return [
            ScenarioListItem(
                name=s["name"],
                description=s["description"],
                default_config=s["default_config"],
            )
            for s in raw
        ]

    async def start_scenario(self, config: ScenarioConfig) -> ScenarioStatus:
        """Start a simulation from a scenario config."""
        try:
            scenario_def = get_scenario(config.scenario_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if simulator.is_running:
            raise HTTPException(
                status_code=409,
                detail="A simulation is already running. Stop it first.",
            )

        setup = scenario_def["setup"]
        await simulator.start(config, setup)

        return ScenarioStatus(**simulator.get_status())

    async def stop_scenario(self) -> ScenarioStatus:
        """Stop the currently running simulation."""
        if not simulator.is_running:
            raise HTTPException(status_code=400, detail="No simulation is running")
        await simulator.stop()
        return ScenarioStatus(**simulator.get_status())

    async def get_status(self) -> ScenarioStatus:
        """Return the current simulation status."""
        return ScenarioStatus(**simulator.get_status())
