from src.economy.utilities.agent_behaviors.base import BaseEconomyAgent, AgentState
from src.economy.utilities.pricing import get_pricing_strategy


class ServiceAgent(BaseEconomyAgent):
    """An agent that offers a capability at a price it computes each tick.

    Places ask orders on the marketplace for each of its capabilities.
    """

    def __init__(self, state: AgentState):
        super().__init__(state)
        self.pricing = get_pricing_strategy(state.pricing_strategy)

    async def decide(self, market_context: dict) -> list[dict]:
        """Place one ask order per capability at the computed price."""
        if not self.state.is_active:
            return []

        orders: list[dict] = []
        for capability in self.state.capabilities:
            price = self.pricing.compute_price(
                self.state.base_price,
                market_context.get(capability, {}),
            )
            orders.append({
                "agent_id": self.state.agent_db_id,
                "side": "ask",
                "capability": capability,
                "price": price,
                "quantity": 1,
            })
        return orders
