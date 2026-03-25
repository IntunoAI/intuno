import logging
import random
import uuid

from src.economy.models.wallet import Transaction
from src.economy.repositories.wallets import WalletRepository
from src.economy.utilities.event_bus import EventBus

log = logging.getLogger("settlement")


class SettlementEngine:
    """Settles trades by transferring credits from buyer to seller.

    Simulates service delivery with a configurable success rate and
    latency distribution.  On failure the buyer keeps their credits.
    """

    def __init__(
        self,
        wallet_repository: WalletRepository,
        event_bus: EventBus,
        success_rate: float = 0.95,
        min_latency_ms: int = 50,
        max_latency_ms: int = 500,
    ):
        self.wallet_repository = wallet_repository
        self.event_bus = event_bus
        self.success_rate = success_rate
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms

    async def settle_trade(
        self,
        buyer_agent_id: uuid.UUID,
        seller_agent_id: uuid.UUID,
        price: int,
        trade_id: uuid.UUID,
        capability: str,
        tick: int = 0,
        emit_events: bool = True,
    ) -> dict:
        """Execute settlement for a single trade.

        Returns a dict with status, latency_ms, and any error detail.
        When *emit_events* is False the caller is responsible for
        publishing outcome events (used by the simulator to emit a
        single composite ``TradeCompleted`` instead).
        """
        latency_ms = random.randint(self.min_latency_ms, self.max_latency_ms)
        succeeded = random.random() < self.success_rate

        if not succeeded:
            if emit_events:
                await self.event_bus.publish("SettlementComplete", {
                    "trade_id": str(trade_id),
                    "buyer_agent_id": str(buyer_agent_id),
                    "seller_agent_id": str(seller_agent_id),
                    "capability": capability,
                    "price": price,
                    "status": "failed",
                    "latency_ms": latency_ms,
                    "tick": tick,
                })
            return {"status": "failed", "latency_ms": latency_ms, "error": "Delivery failed"}

        buyer_wallet = await self.wallet_repository.get_by_agent_id(buyer_agent_id)
        seller_wallet = await self.wallet_repository.get_by_agent_id(seller_agent_id)

        if not buyer_wallet or not seller_wallet:
            return {"status": "error", "latency_ms": 0, "error": "Wallet not found"}

        if buyer_wallet.balance < price:
            if emit_events:
                await self.event_bus.publish("SettlementComplete", {
                    "trade_id": str(trade_id),
                    "buyer_agent_id": str(buyer_agent_id),
                    "seller_agent_id": str(seller_agent_id),
                    "capability": capability,
                    "price": price,
                    "status": "failed",
                    "latency_ms": latency_ms,
                    "tick": tick,
                    "error": "Insufficient buyer balance",
                })
            return {"status": "failed", "latency_ms": latency_ms, "error": "Insufficient balance"}

        reference_id = uuid.uuid4()

        await self.wallet_repository.update_balance(
            buyer_wallet.id, buyer_wallet.balance - price,
        )
        await self.wallet_repository.update_balance(
            seller_wallet.id, seller_wallet.balance + price,
        )

        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=buyer_wallet.id,
                amount=-price,
                tx_type="settlement_debit",
                reference_id=reference_id,
                description=f"Payment for {capability} (trade {trade_id})",
            )
        )
        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=seller_wallet.id,
                amount=price,
                tx_type="settlement_credit",
                reference_id=reference_id,
                description=f"Revenue from {capability} (trade {trade_id})",
            )
        )

        if emit_events:
            await self.event_bus.publish("SettlementComplete", {
                "trade_id": str(trade_id),
                "buyer_agent_id": str(buyer_agent_id),
                "seller_agent_id": str(seller_agent_id),
                "capability": capability,
                "price": price,
                "status": "settled",
                "latency_ms": latency_ms,
                "tick": tick,
            })

        return {"status": "settled", "latency_ms": latency_ms}
