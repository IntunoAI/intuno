from src.economy.utilities.agent_behaviors.base import BaseEconomyAgent, AgentState


class ArbitrageAgent(BaseEconomyAgent):
    """Detects price spreads and places orders to profit from them.

    If the lowest ask for a capability is significantly below the average
    bid, the arbitrageur buys low and resells high.
    """

    def __init__(self, state: AgentState, spread_threshold: float = 0.15):
        super().__init__(state)
        self.spread_threshold = spread_threshold

    async def decide(self, market_context: dict) -> list[dict]:
        """Look for arbitrage opportunities across all capabilities."""
        if not self.state.is_active:
            return []
        if self.state.wallet_balance <= 0:
            return []

        orders: list[dict] = []

        for capability, ctx in market_context.items():
            lowest_ask = ctx.get("lowest_ask")
            avg_bid = ctx.get("avg_bid_price")

            if lowest_ask is None or avg_bid is None:
                continue

            if lowest_ask <= 0:
                continue

            spread = (avg_bid - lowest_ask) / lowest_ask
            if spread < self.spread_threshold:
                continue

            if self.state.wallet_balance < lowest_ask:
                continue

            orders.append({
                "agent_id": self.state.agent_db_id,
                "side": "bid",
                "capability": capability,
                "price": lowest_ask + 1,
                "quantity": 1,
            })

            resell_price = int(avg_bid * 0.95)
            orders.append({
                "agent_id": self.state.agent_db_id,
                "side": "ask",
                "capability": capability,
                "price": resell_price,
                "quantity": 1,
            })

        return orders
