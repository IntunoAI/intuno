import asyncio
import logging
import uuid
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import async_session_factory
from src.models.registry import Agent
from src.economy.models.order import Order
from src.economy.models.wallet import Transaction, Wallet
from src.economy.repositories.agents import AgentRepository
from src.economy.repositories.market import MarketRepository
from src.economy.repositories.wallets import WalletRepository
from src.economy.schemas.scenario import ScenarioConfig
from src.economy.utilities.agent_behaviors.base import AgentState, BaseEconomyAgent
from src.economy.utilities.agent_behaviors.buyer_agent import BuyerAgent
from src.economy.utilities.agent_behaviors.service_agent import ServiceAgent
from src.economy.utilities.event_bus import EventBus, event_bus
from src.economy.utilities.settlement import SettlementEngine

log = logging.getLogger("simulator")

NO_LIMIT = 50_000


class Simulator:
    """Tick-based simulation runner.

    Each tick: agents observe -> decide -> orders placed -> matching ->
    settlement -> events emitted.  The simulator manages its own DB
    sessions to avoid coupling with HTTP request lifecycles.
    """

    def __init__(self):
        self.event_bus: EventBus = event_bus
        self.status: str = "idle"
        self.current_tick: int = 0
        self.total_ticks: int = 0
        self.scenario_name: str = ""
        self.agents: list[BaseEconomyAgent] = []
        self.capabilities: list[str] = []
        self._task: asyncio.Task | None = None
        self._total_trades: int = 0
        self._total_volume: int = 0

    @property
    def is_running(self) -> bool:
        """Check if a simulation is currently active."""
        return self.status == "running"

    async def start(self, config: ScenarioConfig, scenario_setup: dict) -> None:
        """Launch a simulation in the background."""
        if self.is_running:
            raise RuntimeError("Simulation already running")

        self.scenario_name = config.scenario_name
        self.total_ticks = config.tick_count
        self.current_tick = 0
        self.status = "running"
        self._total_trades = 0
        self._total_volume = 0
        self.capabilities = scenario_setup.get("capabilities", ["translation"])

        async with async_session_factory() as session:
            cancelled = await self._cancel_stale_orders(session)
            if cancelled:
                log.info("Cancelled %d stale open orders from previous runs", cancelled)
            await self._provision_agents(session, config, scenario_setup)
            await session.commit()

        log.info(
            "Starting simulation '%s': %d ticks, %d agents (%s), capabilities=%s",
            config.scenario_name,
            config.tick_count,
            len(self.agents),
            f"{config.service_agent_count}S+{config.buyer_agent_count}B",
            self.capabilities,
        )

        await self.event_bus.publish("SimulationStarted", {
            "scenario_name": config.scenario_name,
            "total_ticks": config.tick_count,
            "agents_count": len(self.agents),
        })

        self._task = asyncio.create_task(self._run_loop(config))

    async def stop(self) -> None:
        """Gracefully stop a running simulation."""
        self.status = "stopped"
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        log.info("Simulation stopped at tick %d", self.current_tick)
        await self.event_bus.publish("SimulationStopped", {
            "scenario_name": self.scenario_name,
            "final_tick": self.current_tick,
        })

    def get_status(self) -> dict:
        """Return current simulation state."""
        return {
            "scenario_name": self.scenario_name,
            "status": self.status,
            "current_tick": self.current_tick,
            "total_ticks": self.total_ticks,
            "agents_count": len(self.agents),
            "total_trades": self._total_trades,
            "total_volume": self._total_volume,
        }

    async def _run_loop(self, config: ScenarioConfig) -> None:
        """Main simulation loop executing one tick at a time."""
        try:
            for tick in range(1, config.tick_count + 1):
                if self.status != "running":
                    break

                self.current_tick = tick
                async with async_session_factory() as session:
                    await self._execute_tick(session, tick)
                    await session.commit()

                await self.event_bus.publish("SimulationTick", {
                    "tick": tick,
                    "total_ticks": config.tick_count,
                })

                await asyncio.sleep(config.tick_interval_ms / 1000.0)

            self.status = "completed"
            log.info(
                "Simulation completed: %d ticks, %d trades, %d volume",
                self.current_tick, self._total_trades, self._total_volume,
            )
            await self.event_bus.publish("SimulationCompleted", {
                "scenario_name": self.scenario_name,
                "total_ticks": self.current_tick,
                "total_trades": self._total_trades,
                "total_volume": self._total_volume,
            })
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.status = "error"
            log.exception("Simulation error at tick %d", self.current_tick)
            await self.event_bus.publish("SimulationError", {
                "error": str(exc),
                "tick": self.current_tick,
            })

    async def _execute_tick(self, session: AsyncSession, tick: int) -> None:
        """Run a single simulation tick."""
        wallet_repo = WalletRepository(db_session=session)
        market_repo = MarketRepository(db_session=session)
        settlement_engine = SettlementEngine(
            wallet_repository=wallet_repo,
            event_bus=self.event_bus,
        )

        market_context = await self._build_market_context(market_repo)

        for agent in self.agents:
            wallet = await wallet_repo.get_by_agent_id(agent.state.agent_db_id)
            if wallet:
                agent.update_state(wallet_balance=wallet.balance)

        all_orders: list[dict] = []
        for agent in self.agents:
            orders = await agent.decide(market_context)
            all_orders.extend(orders)

        bids_placed = sum(1 for o in all_orders if o["side"] == "bid")
        asks_placed = sum(1 for o in all_orders if o["side"] == "ask")

        for order_data in all_orders:
            order = Order(
                agent_id=order_data["agent_id"],
                side=order_data["side"],
                capability=order_data["capability"],
                price=order_data["price"],
                quantity=order_data.get("quantity", 1),
                tick=tick,
            )
            await market_repo.create_order(order)

        tick_trades = 0
        tick_volume = 0
        for capability in self.capabilities:
            trades = await self._match_and_settle(
                market_repo, settlement_engine, capability, tick,
            )
            tick_trades += len(trades)
            tick_volume += sum(t["price"] for t in trades)

        self._total_trades += tick_trades
        self._total_volume += tick_volume

        if tick <= 3 or tick % 10 == 0 or tick_trades > 0:
            ctx = market_context.get(self.capabilities[0], {})
            log.info(
                "tick=%d | orders=%d (bids=%d asks=%d) | matched=%d vol=%d | "
                "ctx: avg_ask=%d avg_bid=%d open_bids=%d open_asks=%d",
                tick, len(all_orders), bids_placed, asks_placed,
                tick_trades, tick_volume,
                ctx.get("avg_ask_price", 0), ctx.get("avg_bid_price", 0),
                ctx.get("bid_count", 0), ctx.get("ask_count", 0),
            )

    async def _match_and_settle(
        self,
        market_repo: MarketRepository,
        settlement_engine: SettlementEngine,
        capability: str,
        tick: int,
    ) -> list[dict]:
        """Match orders and settle resulting trades for one capability."""
        bids = await market_repo.list_open_orders(
            capability=capability, side="bid", limit=NO_LIMIT,
        )
        asks = await market_repo.list_open_orders(
            capability=capability, side="ask", limit=NO_LIMIT,
        )

        bids_sorted = sorted(bids, key=lambda o: (-o.price, o.created_at))
        asks_sorted = sorted(asks, key=lambda o: (o.price, o.created_at))

        results: list[dict] = []
        bid_idx = 0
        ask_idx = 0

        while bid_idx < len(bids_sorted) and ask_idx < len(asks_sorted):
            bid = bids_sorted[bid_idx]
            ask = asks_sorted[ask_idx]

            if bid.price < ask.price:
                break

            execution_price = ask.price

            from src.economy.models.order import Trade
            trade = Trade(
                bid_order_id=bid.id,
                ask_order_id=ask.id,
                buyer_agent_id=bid.agent_id,
                seller_agent_id=ask.agent_id,
                capability=capability,
                price=execution_price,
                tick=tick,
            )
            trade = await market_repo.create_trade(trade)

            await market_repo.update_order_status(bid.id, "filled")
            await market_repo.update_order_status(ask.id, "filled")

            settlement_result = await settlement_engine.settle_trade(
                buyer_agent_id=bid.agent_id,
                seller_agent_id=ask.agent_id,
                price=execution_price,
                trade_id=trade.id,
                capability=capability,
                tick=tick,
                emit_events=False,
            )

            trade.latency_ms = settlement_result.get("latency_ms", 0)
            trade.status = settlement_result.get("status", "settled")

            await self.event_bus.publish("TradeCompleted", {
                "trade_id": str(trade.id),
                "buyer_agent_id": str(bid.agent_id),
                "seller_agent_id": str(ask.agent_id),
                "capability": capability,
                "price": execution_price,
                "status": settlement_result.get("status", "settled"),
                "latency_ms": settlement_result.get("latency_ms", 0),
                "tick": tick,
            })

            results.append({"price": execution_price, **settlement_result})
            bid_idx += 1
            ask_idx += 1

        return results

    async def _build_market_context(self, market_repo: MarketRepository) -> dict:
        """Build per-capability market context from open orders."""
        context: dict[str, dict] = {}
        for capability in self.capabilities:
            bids = await market_repo.list_open_orders(
                capability=capability, side="bid", limit=NO_LIMIT,
            )
            asks = await market_repo.list_open_orders(
                capability=capability, side="ask", limit=NO_LIMIT,
            )

            bid_prices = [o.price for o in bids]
            ask_prices = [o.price for o in asks]

            context[capability] = {
                "bid_count": len(bids),
                "ask_count": len(asks),
                "avg_bid_price": sum(bid_prices) / len(bid_prices) if bid_prices else 0,
                "avg_ask_price": sum(ask_prices) / len(ask_prices) if ask_prices else 0,
                "lowest_ask": min(ask_prices) if ask_prices else None,
                "highest_bid": max(bid_prices) if bid_prices else None,
                "demand_ratio": len(bids) / max(len(asks), 1),
            }
        return context

    @staticmethod
    async def _cancel_stale_orders(session: AsyncSession) -> int:
        """Cancel all open orders left over from previous simulation runs."""
        result = await session.execute(
            update(Order)
            .where(Order.status == "open")
            .values(status="cancelled")
        )
        return result.rowcount  # type: ignore[return-value]

    async def _provision_agents(
        self,
        session: AsyncSession,
        config: ScenarioConfig,
        scenario_setup: dict,
    ) -> None:
        """Create agent and wallet DB records, then instantiate behaviors."""
        agent_repo = AgentRepository(db_session=session)
        wallet_repo = WalletRepository(db_session=session)
        self.agents = []

        capabilities = scenario_setup.get("capabilities", ["translation"])
        service_strategies = scenario_setup.get("service_pricing", "fixed")

        for i in range(config.service_agent_count):
            base_price = scenario_setup.get("base_price", 100) + (i * 10)
            agent = Agent(
                agent_id=f"service-{uuid.uuid4().hex[:8]}",
                name=f"Service Agent {i + 1}",
                description=f"Provides {', '.join(capabilities)}",
                tags=capabilities,
                pricing_strategy=service_strategies,
                base_price=float(base_price),
                invoke_endpoint="https://simulator.internal/noop",
                auth_type="public",
                version="1.0.0",
                trust_verification="self-signed",
                user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            )
            agent = await agent_repo.create(agent)
            wallet = Wallet(agent_id=agent.id, balance=0)
            wallet = await wallet_repo.create(wallet)
            await self._grant_initial_balance(
                wallet_repo, wallet.id, config.initial_balance,
            )

            state = AgentState(
                agent_db_id=agent.id,
                agent_id=agent.agent_id,
                name=agent.name,
                capabilities=capabilities,
                pricing_strategy=service_strategies,
                base_price=base_price,
                wallet_balance=config.initial_balance,
            )
            self.agents.append(ServiceAgent(state))

        for i in range(config.buyer_agent_count):
            agent = Agent(
                agent_id=f"buyer-{uuid.uuid4().hex[:8]}",
                name=f"Buyer Agent {i + 1}",
                description=f"Needs {', '.join(capabilities)}",
                tags=capabilities,
                pricing_strategy="fixed",
                base_price=float(scenario_setup.get("buyer_budget", 120)),
                invoke_endpoint="https://simulator.internal/noop",
                auth_type="public",
                version="1.0.0",
                trust_verification="self-signed",
                user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            )
            agent = await agent_repo.create(agent)
            wallet = Wallet(agent_id=agent.id, balance=0)
            wallet = await wallet_repo.create(wallet)
            await self._grant_initial_balance(
                wallet_repo, wallet.id, config.initial_balance,
            )

            state = AgentState(
                agent_db_id=agent.id,
                agent_id=agent.agent_id,
                name=agent.name,
                capabilities=capabilities,
                pricing_strategy="fixed",
                base_price=scenario_setup.get("buyer_budget", 120),
                wallet_balance=config.initial_balance,
            )
            self.agents.append(BuyerAgent(state, needs=capabilities))

        log.info(
            "Provisioned %d service agents + %d buyer agents",
            config.service_agent_count, config.buyer_agent_count,
        )

    @staticmethod
    async def _grant_initial_balance(
        wallet_repo: WalletRepository,
        wallet_id: uuid.UUID,
        amount: int,
    ) -> None:
        """Record the simulation's initial balance as a grant with a full audit trail."""
        if amount <= 0:
            return
        await wallet_repo.update_balance(wallet_id, amount)
        await wallet_repo.create_transaction(
            Transaction(
                wallet_id=wallet_id,
                amount=amount,
                tx_type="grant_promotional",
                description="Simulation initial balance",
            )
        )


simulator = Simulator()
