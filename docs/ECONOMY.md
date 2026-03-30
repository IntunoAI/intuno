# Economy Module

The economy module (`src/economy/`) implements an agent-to-agent marketplace with wallets, an order-book exchange, and credit purchasing. It is self-contained and layered: routes → services → repositories → models.

---

## 1. Overview

Agents in the Intuno network can charge other agents for their services. The economy module provides:

- **Wallets & ledger** — every user and every agent has a wallet; all movements are recorded as immutable transactions.
- **Marketplace** — agents post bids (buy) and asks (sell) for named capabilities; an order-matching engine settles trades.
- **Credit purchasing** — users top up their wallet via a simulated checkout flow (Stripe-style pending → confirmed lifecycle).
- **WebSocket stream** — real-time event feed for dashboards.

---

## 2. Data Model

### Wallet

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `wallet_type` | `user` \| `agent` | Exactly one owner field must be set |
| `user_id` | UUID FK | Set for user wallets |
| `agent_id` | UUID FK | Set for agent wallets |
| `balance` | int | Credits (never negative) |

### Transaction (immutable ledger)

Every credit movement produces at least one `Transaction` row. Transfers produce two rows sharing a `reference_id` (double-entry).

| Field | Notes |
|---|---|
| `tx_type` | `grant_welcome`, `grant_promotional`, `grant_reward`, `purchase`, `debit`, `credit`, `transfer_in`, `transfer_out`, `earned`, `spent` |
| `amount` | Positive = credit, negative = debit |
| `reference_id` | Links the two legs of a double-entry transfer |

### Order

Represents an open bid or ask on the marketplace.

| Field | Notes |
|---|---|
| `side` | `bid` (buy) or `ask` (sell) |
| `capability` | The service being traded (string tag) |
| `price` | Credits per unit |
| `status` | `open` → `filled` or `cancelled` |
| `tick` | Simulation tick when the order was placed |

### Trade

Created when a bid and ask are matched.

| Field | Notes |
|---|---|
| `status` | `settled` or `failed` |
| `price` | Execution price (ask price, seller's benefit) |
| `latency_ms` | Simulated settlement latency |

### CreditPurchase

Tracks the checkout lifecycle.

| Status | Meaning |
|---|---|
| `pending` | Purchase initiated, awaiting confirmation |
| `completed` | Payment confirmed, credits added to wallet |
| `failed` | Cancelled or payment declined |
| `refunded` | Credits reversed |

---

## 3. Credit Lifecycle

```
User registers
   └─► wallet auto-created (balance = 0)
         │
         ▼
POST /wallets/{id}/grant          ← welcome / promotional grant
         │
         ▼
POST /credits/wallets/{id}/purchase   ← status: pending
         │
         ▼
POST /credits/purchases/{id}/confirm  ← status: completed, balance += credits
         │
         ▼
POST /broker/invoke (priced agent)    ← balance -= base_price (if pricing_enabled)
```

- Grants are free credits given by the platform (welcome bonus, promotions, rewards).
- Purchases simulate a payment provider: create a `pending` record, then confirm it (or cancel it).
- Broker invocations deduct `base_price` credits atomically; insufficient balance → HTTP 402.

---

## 4. Marketplace Mechanics

### Order placement

Any agent with a known DB UUID can post an order via `POST /market/orders`. In practice, orders are placed by simulator agents (the `/market/orders` endpoint is public but requires a valid `agent_id`).

### Matching

`MarketService.match_orders(capability, tick)` runs price-time priority matching:

1. Collect all `open` bids for the capability, sort descending by price.
2. Collect all `open` asks, sort ascending by price.
3. For each bid/ask pair where `bid.price >= ask.price`:
   - Execute at **ask price** (seller sets the price).
   - Mark both orders `filled`.
   - Create a `Trade` record.
   - Settle immediately via `SettlementEngine`.

### Settlement

`SettlementEngine.settle_trade()` transfers credits from the buyer agent's wallet to the seller agent's wallet using double-entry bookkeeping. Outcomes:

- **Success (95% rate):** `atomic_debit(buyer)` + `atomic_credit(seller)` with shared `reference_id`; trade status → `settled`.
- **Insufficient balance:** trade status → `failed`; no credit movement.
- **Random failure (5%):** simulates real-world payment uncertainty; trade status → `failed`.

Settlement publishes a `SettlementComplete` event with `latency_ms` drawn from a uniform distribution (50–500 ms by default).

---

## 5. Event Bus & WebSocket

`EventBus` (`utilities/event_bus.py`) is an in-memory pub/sub broker. Components call `event_bus.publish(event_type, data)` and the bus:

1. Calls all registered async callbacks (e.g. logging, metrics).
2. Broadcasts the event to all connected WebSocket clients as JSON.

Connect to `ws://<host>/ws/events` to receive the stream. Each message is:

```json
{ "event": "TradeCompleted", "data": { "trade_id": "...", "price": 80 }, "timestamp": "2026-03-26T10:00:00Z" }
```

See [API_ENDPOINTS.md](API_ENDPOINTS.md#websocket) for the full event type table.

---

## 6. Running Tests

```bash
# 1. Start backend
cd wisdom && uvicorn src.main:app --reload --port 8000

# 2. Run economy e2e tests
python -m tests.test_economy --base-url http://localhost:8000
```

The test runner (`tests/test_economy.py`) covers four phases: wallets, credits, consolidation, and edge cases.

---

## 7. Known Gaps

| Gap | Details |
|---|---|
| **agents route not mounted** | `src/economy/routes/agents.py` provides CRUD for economy agents but is not included in `main.py`. |
| **No orchestrator integration** | The orchestrator (`utilities/orchestrator.py`) does not yet deduct credits when invoking priced agents through multi-step task plans. |
| **No usage-based billing** | Credits are deducted only at broker-invoke time. |
| **Simulated payments only** | `PurchaseService` generates a fake `provider_reference`; no real Stripe or payment provider is wired up. |
