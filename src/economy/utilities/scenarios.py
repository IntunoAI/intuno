from src.economy.schemas.scenario import ScenarioConfig


SCENARIOS: dict[str, dict] = {
    "price_discovery": {
        "description": (
            "5 service agents offer 'translation' at different base prices. "
            "10 buyer agents each have a budget. Run 100 ticks and observe "
            "price convergence as the market finds equilibrium."
        ),
        "default_config": ScenarioConfig(
            scenario_name="price_discovery",
            tick_count=100,
            tick_interval_ms=500,
            service_agent_count=5,
            buyer_agent_count=10,
            initial_balance=1000,
        ),
        "setup": {
            "capabilities": ["translation"],
            "service_pricing": "fixed",
            "base_price": 80,
            "buyer_budget": 120,
        },
    },
    "supply_shock": {
        "description": (
            "Starts like price_discovery but mid-simulation 2 of 5 service "
            "agents go offline. Observe the price spike and recovery as "
            "remaining agents adjust using dynamic pricing."
        ),
        "default_config": ScenarioConfig(
            scenario_name="supply_shock",
            tick_count=150,
            tick_interval_ms=400,
            service_agent_count=5,
            buyer_agent_count=10,
            initial_balance=1500,
        ),
        "setup": {
            "capabilities": ["summarization"],
            "service_pricing": "dynamic",
            "base_price": 100,
            "buyer_budget": 150,
            "shock_at_tick": 50,
            "agents_to_disable": 2,
        },
    },
    "arbitrage": {
        "description": (
            "Two groups of service agents price 'analysis' very differently. "
            "An arbitrage agent detects the spread and tries to profit. "
            "Does the market correct?"
        ),
        "default_config": ScenarioConfig(
            scenario_name="arbitrage",
            tick_count=120,
            tick_interval_ms=400,
            service_agent_count=6,
            buyer_agent_count=8,
            initial_balance=2000,
        ),
        "setup": {
            "capabilities": ["analysis"],
            "service_pricing": "fixed",
            "base_price": 60,
            "buyer_budget": 200,
            "include_arbitrageur": True,
        },
    },
    "reputation_premium": {
        "description": (
            "Agents with higher success rates charge more. Buyers prefer "
            "quality over price up to a threshold. Does reputation-based "
            "pricing produce a viable market?"
        ),
        "default_config": ScenarioConfig(
            scenario_name="reputation_premium",
            tick_count=100,
            tick_interval_ms=500,
            service_agent_count=5,
            buyer_agent_count=12,
            initial_balance=1200,
        ),
        "setup": {
            "capabilities": ["translation", "summarization"],
            "service_pricing": "dynamic",
            "base_price": 90,
            "buyer_budget": 140,
        },
    },
}


def get_scenario(name: str) -> dict:
    """Return a scenario definition by name, or raise ValueError."""
    scenario = SCENARIOS.get(name)
    if not scenario:
        available = ", ".join(SCENARIOS.keys())
        raise ValueError(f"Unknown scenario '{name}'. Available: {available}")
    return scenario


def list_scenarios() -> list[dict]:
    """Return all available scenarios with their descriptions and defaults."""
    return [
        {
            "name": name,
            "description": data["description"],
            "default_config": data["default_config"],
        }
        for name, data in SCENARIOS.items()
    ]
