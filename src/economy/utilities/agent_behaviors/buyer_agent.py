import random

from src.economy.utilities.agent_behaviors.base import BaseEconomyAgent, AgentState


class BuyerAgent(BaseEconomyAgent):
    """An agent that needs capabilities and places bid orders.

    Each tick the buyer picks a random capability it needs and bids
    at a price within its budget, factoring in the market context.
    """

    def __init__(self, state: AgentState, needs: list[str] | None = None):
        super().__init__(state)
        self.needs = needs or state.capabilities

    async def decide(self, market_context: dict) -> list[dict]:
        """Place a bid for a randomly selected needed capability."""
        if not self.state.is_active or not self.needs:
            return []

        if self.state.wallet_balance <= 0:
            return []

        capability = random.choice(self.needs)
        cap_context = market_context.get(capability, {})
        avg_ask_price = cap_context.get("avg_ask_price", self.state.base_price)

        bid_price = int(avg_ask_price * random.uniform(0.8, 1.2))
        bid_price = max(1, min(bid_price, self.state.wallet_balance))

        return [{
            "agent_id": self.state.agent_db_id,
            "side": "bid",
            "capability": capability,
            "price": bid_price,
            "quantity": 1,
        }]
