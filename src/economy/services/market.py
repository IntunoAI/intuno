import uuid

from fastapi import Depends, HTTPException

from src.economy.models.order import Order, Trade
from src.economy.repositories.market import MarketRepository
from src.economy.repositories.wallets import WalletRepository
from src.economy.schemas.market import (
    OrderBookResponse,
    OrderCreate,
    OrderResponse,
    TradeResponse,
)
from src.economy.utilities.event_bus import EventBus, event_bus


class MarketService:
    """Marketplace business logic: order placement, matching, and trade history."""

    def __init__(
        self,
        market_repository: MarketRepository = Depends(),
        wallet_repository: WalletRepository = Depends(),
    ):
        self.market_repository = market_repository
        self.wallet_repository = wallet_repository
        self.event_bus: EventBus = event_bus

    async def place_order(self, payload: OrderCreate) -> OrderResponse:
        """Place a bid or ask on the marketplace."""
        order = Order(
            agent_id=payload.agent_id,
            side=payload.side,
            capability=payload.capability,
            price=payload.price,
            quantity=payload.quantity,
        )
        order = await self.market_repository.create_order(order)

        await self.event_bus.publish("OrderPlaced", {
            "order_id": str(order.id),
            "agent_id": str(order.agent_id),
            "side": order.side,
            "capability": order.capability,
            "price": order.price,
        })

        return OrderResponse.model_validate(order)

    async def match_orders(self, capability: str, tick: int = 0) -> list[TradeResponse]:
        """Run price-time priority matching for a given capability.

        Matches the highest bid against the lowest ask when bid >= ask.
        Execution price is the ask price (seller gets their asking price).
        """
        bids = await self.market_repository.list_open_orders(
            capability=capability, side="bid",
        )
        asks = await self.market_repository.list_open_orders(
            capability=capability, side="ask",
        )

        bids_sorted = sorted(bids, key=lambda o: (-o.price, o.created_at))
        asks_sorted = sorted(asks, key=lambda o: (o.price, o.created_at))

        trades: list[TradeResponse] = []

        bid_idx = 0
        ask_idx = 0
        while bid_idx < len(bids_sorted) and ask_idx < len(asks_sorted):
            bid = bids_sorted[bid_idx]
            ask = asks_sorted[ask_idx]

            if bid.price < ask.price:
                break

            execution_price = ask.price

            trade = Trade(
                bid_order_id=bid.id,
                ask_order_id=ask.id,
                buyer_agent_id=bid.agent_id,
                seller_agent_id=ask.agent_id,
                capability=capability,
                price=execution_price,
                tick=tick,
            )
            trade = await self.market_repository.create_trade(trade)

            await self.market_repository.update_order_status(bid.id, "filled")
            await self.market_repository.update_order_status(ask.id, "filled")

            await self.event_bus.publish("TradeMatched", {
                "trade_id": str(trade.id),
                "buyer_agent_id": str(trade.buyer_agent_id),
                "seller_agent_id": str(trade.seller_agent_id),
                "capability": capability,
                "price": execution_price,
                "tick": tick,
            })

            trades.append(TradeResponse.model_validate(trade))
            bid_idx += 1
            ask_idx += 1

        return trades

    async def get_order_book(self, capability: str) -> OrderBookResponse:
        """Return the current open bids and asks for a capability."""
        bids = await self.market_repository.list_open_orders(
            capability=capability, side="bid",
        )
        asks = await self.market_repository.list_open_orders(
            capability=capability, side="ask",
        )
        return OrderBookResponse(
            capability=capability,
            bids=[OrderResponse.model_validate(o) for o in sorted(bids, key=lambda o: -o.price)],
            asks=[OrderResponse.model_validate(o) for o in sorted(asks, key=lambda o: o.price)],
        )

    async def list_trades(
        self,
        capability: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TradeResponse]:
        """Return recent trades."""
        trades = await self.market_repository.list_trades(
            capability=capability, limit=limit, offset=offset,
        )
        return [TradeResponse.model_validate(t) for t in trades]
