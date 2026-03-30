import abc
import random


class PricingStrategy(abc.ABC):
    """Base class for agent pricing strategies."""

    @abc.abstractmethod
    def compute_price(self, base_price: int, context: dict) -> int:
        """Return the price to quote given the current market context."""
        ...


class FixedPricing(PricingStrategy):
    """Always returns the agent's base price."""

    def compute_price(self, base_price: int, context: dict) -> int:
        """Return the base price unchanged."""
        return base_price


class DynamicPricing(PricingStrategy):
    """Adjusts price based on demand signals.

    When demand_ratio > 1 (more bids than asks), price increases.
    When demand_ratio < 1, price decreases toward a floor.
    """

    def __init__(self, sensitivity: float = 0.2, floor_pct: float = 0.5):
        self.sensitivity = sensitivity
        self.floor_pct = floor_pct

    def compute_price(self, base_price: int, context: dict) -> int:
        """Scale price by demand ratio with a floor."""
        demand_ratio = context.get("demand_ratio", 1.0)
        adjustment = 1.0 + self.sensitivity * (demand_ratio - 1.0)
        floor = int(base_price * self.floor_pct)
        return max(floor, int(base_price * adjustment))


class AuctionPricing(PricingStrategy):
    """Vickrey (second-price) auction strategy.

    The agent bids their true valuation. In a Vickrey auction the winner
    pays the second-highest bid, so truthful bidding is dominant.
    """

    def __init__(self, valuation_noise: float = 0.1):
        self.valuation_noise = valuation_noise

    def compute_price(self, base_price: int, context: dict) -> int:
        """Return true valuation with small random noise."""
        noise = random.uniform(
            -self.valuation_noise, self.valuation_noise,
        )
        return max(1, int(base_price * (1.0 + noise)))


PRICING_STRATEGIES: dict[str, type[PricingStrategy]] = {
    "fixed": FixedPricing,
    "dynamic": DynamicPricing,
    "auction": AuctionPricing,
}


def get_pricing_strategy(name: str) -> PricingStrategy:
    """Instantiate a pricing strategy by name."""
    strategy_class = PRICING_STRATEGIES.get(name)
    if not strategy_class:
        raise ValueError(f"Unknown pricing strategy: {name}")
    return strategy_class()
