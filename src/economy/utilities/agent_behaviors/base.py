import abc
import uuid
from dataclasses import dataclass, field


@dataclass
class AgentState:
    """Snapshot of an agent's economic state within a simulation tick."""

    agent_db_id: uuid.UUID
    agent_id: str
    name: str
    capabilities: list[str]
    pricing_strategy: str
    base_price: int
    wallet_balance: int
    success_rate: float = 1.0
    total_trades: int = 0
    is_active: bool = True


class BaseEconomyAgent(abc.ABC):
    """Abstract base for all simulated agent behaviors.

    Each agent observes the market, decides what orders to place, and
    updates its internal state after each tick.
    """

    def __init__(self, state: AgentState):
        self.state = state

    @abc.abstractmethod
    async def decide(self, market_context: dict) -> list[dict]:
        """Return a list of order dicts to place this tick.

        Each dict must include: side, capability, price, quantity.
        """
        ...

    def update_state(self, **kwargs) -> None:
        """Apply post-tick state updates."""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
