# Intuno API Endpoints

## Authentication

### POST /auth/register
Register a new user
- **Body**: `UserRegister` (email, password, first_name?, last_name?)
- **Response**: `UserResponse`

### POST /auth/login
Login and get access token
- **Body**: `UserLogin` (email, password)
- **Response**: `TokenResponse` (access_token, token_type, expires_in)

### POST /auth/api-keys
Create a new API key (requires authentication)
- **Body**: `ApiKeyCreate` (name, expires_at?)
- **Response**: `ApiKeyResponse` (includes the actual key)

### GET /auth/api-keys
List user's API keys (requires authentication)
- **Response**: `List[ApiKeyListResponse]`

### DELETE /auth/api-keys/{key_id}
Delete an API key (requires authentication)
- **Response**: 204 No Content

### GET /auth/me
Get current user information (requires authentication)
- **Response**: `UserResponse`

## Registry

### POST /registry/agents
Register a new agent (requires authentication)
- **Body**: `AgentRegistration`
  - `name`, `description`, `endpoint` (required)
  - `auth_type`: `public` | `api_key` | `bearer_token` (default `public`)
  - `tags`, `category`, `input_schema` (optional)
  - `base_price`: integer credits per invocation (optional, default `null` = free)
  - `pricing_enabled`: boolean — opt this agent into credit billing (default `false`)
- **Response**: `AgentResponse`

### GET /registry/agents
List and search agents
- **Query params**:
  - `tags`: List[str] - filter by tags
  - `capability`: str - filter by capability
  - `search`: str - text search
  - `limit`: int (1-100, default 20)
  - `offset`: int (default 0)
- **Response**: `List[AgentListResponse]`

### GET /registry/agents/{agent_id}
Get agent details by agent_id
- **Response**: `AgentResponse`

### PUT /registry/agents/{agent_uuid}
Update an agent (owner only, requires authentication)
- **Body**: `AgentUpdate` (manifest)
- **Response**: `AgentResponse`

### DELETE /registry/agents/{agent_uuid}
Delete an agent (owner only, requires authentication)
- **Response**: 204 No Content

### GET /registry/discover
Semantic discovery of agents
- **Query params**:
  - `query`: str - natural language query
  - `limit`: int (1-50, default 10)
- **Response**: `List[AgentListResponse]`

### GET /registry/my-agents
Get current user's agents (requires authentication)
- **Response**: `List[AgentListResponse]`

## Broker

### POST /broker/invoke
Invoke an agent through the broker (requires authentication)
- **Body**: `InvokeRequest`
  - `agent_id` (string, required)
  - `input` (object, optional)
  - `conversation_id`, `message_id`, `external_user_id` (optional)
- **Response**: `InvokeResponse`
  - `success`, `data`, `error`, `latency_ms`, `status_code`
  - `credits_charged` (integer | null) — credits deducted when agent has `pricing_enabled=true`
- **402 Payment Required** — returned when the target agent has `pricing_enabled=true` and the caller's wallet has insufficient credits

### GET /broker/logs
Get invocation logs for the current user (requires authentication)
- **Query params**: `limit`: int (1-100, default 50)
- **Response**: `List[InvocationLogResponse]`

### GET /broker/logs/agent/{agent_id}
Get invocation logs for a specific agent (requires authentication)
- **Query params**: `limit`: int (1-100, default 50)
- **Response**: `List[InvocationLogResponse]`

## Economy

Credits are the billing unit for agent invocations. Humans fund wallets; agents spend credits to call other agents.

> **Note:** `src/economy/routes/agents.py` exists in the codebase but is **not mounted** in `main.py`. Economy agents are provisioned automatically by the scenario simulator — there is no public REST API for creating or listing them directly.

### Billing flow
1. Register an agent with `base_price` (integer credits) and `pricing_enabled: true`
2. Fund the caller's wallet via the credits purchase flow
3. `POST /broker/invoke` → broker checks balance → deducts on success → returns `credits_charged`

---

## Wallets (`/wallets`)

### GET /wallets/me
Get the authenticated user's main wallet
- **Auth**: JWT required
- **Response**: `WalletResponse` (`id`, `user_id`, `wallet_type`, `balance`, `created_at`, `updated_at`)

### GET /wallets/me/agents
List all agent wallets owned by the authenticated user
- **Auth**: JWT required
- **Response**: `List[WalletResponse]`

### GET /wallets/me/overview
User wallet plus all associated agent wallet summaries
- **Auth**: JWT required
- **Response**: `UserWalletOverview` (`wallet`, `agent_wallets`, `total_agent_balance`)

### POST /wallets/me/consolidate
Sweep all agent wallet balances into the user's main wallet
- **Auth**: JWT required
- **Body**: `{ "agent_ids": ["<uuid>", ...] }` — omit `agent_ids` to sweep all agent wallets
- **Response**: `ConsolidateResponse` (`reference_id`, `total_swept`, `wallets_swept`)

### GET /wallets
List all wallets ordered by balance (admin)
- **Query params**: `limit` (1–200, default 100)
- **Response**: `List[WalletResponse]`

### GET /wallets/{wallet_id}
Get a wallet by ID
- **Response**: `WalletResponse`

### GET /wallets/agent/{agent_id}
Get the wallet for a specific agent
- **Response**: `WalletResponse`

### POST /wallets/{wallet_id}/credit
Add credits to a wallet
- **Auth**: JWT required
- **Body**: `{ "amount": <int gt 0>, "description": "<optional>" }`
- **Response**: `WalletResponse` (updated balance)

### POST /wallets/{wallet_id}/debit
Remove credits from a wallet; fails with 4xx if balance is insufficient
- **Auth**: JWT required
- **Body**: `{ "amount": <int gt 0>, "description": "<optional>" }`
- **Response**: `WalletResponse` (updated balance)

### POST /wallets/transfer
Transfer credits between two wallets (double-entry)
- **Auth**: JWT required
- **Body**: `{ "from_wallet_id": "<uuid>", "to_wallet_id": "<uuid>", "amount": <int gt 0>, "description": "<optional>" }`
- **Response**: `{ "from_wallet": WalletResponse, "to_wallet": WalletResponse, "reference_id": "<uuid>" }`

### POST /wallets/{wallet_id}/grant
Grant promotional/reward/welcome credits
- **Body**: `{ "amount": <int gt 0>, "grant_type": "grant_welcome|grant_promotional|grant_reward", "description": "<optional>" }`
- **Response**: `WalletResponse` (updated balance)

### GET /wallets/{wallet_id}/summary
Balance breakdown by credit source
- **Response**: `WalletSummary` (`wallet_id`, `balance`, `total_granted`, `total_purchased`, `total_earned`, `total_spent`, `transaction_count`)

### GET /wallets/{wallet_id}/transactions
Paginated ledger history
- **Query params**: `limit` (1–200, default 50), `offset` (default 0)
- **Response**: `List[TransactionResponse]` (`id`, `wallet_id`, `amount`, `tx_type`, `reference_id`, `description`, `created_at`)

---

## Credits (`/credits`)

### GET /credits/packages
List available credit packages (configured via `ECONOMY_CREDIT_PACKAGES` env var)
- **Response**: `List[CreditPackageResponse]` (`id`, `credits`, `price_cents`, `label`)

### POST /credits/wallets/{wallet_id}/purchase
Initiate a credit purchase (simulates Stripe checkout)
- **Body**: `{ "package_id": "<string>" }`
- **Response**: `PurchaseResponse` (status: `pending`)

### POST /credits/purchases/{purchase_id}/confirm
Confirm a pending purchase — credits are added to the wallet (simulates Stripe webhook)
- **Response**: `PurchaseResponse` (status: `completed`)
- **4xx** if purchase is not in `pending` state

### POST /credits/purchases/{purchase_id}/cancel
Cancel a pending purchase
- **Response**: `PurchaseResponse` (status: `failed`)

---

## Market (`/market`)

### GET /market/capabilities
List agents with `pricing_enabled=true` — the service catalog
- **No auth required**
- **Response**: `List[PricedAgentResponse]` (`agent_id`, `name`, `description`, `tags`, `base_price`, `invocation_count`)

### POST /market/orders
Place a bid or ask order on the marketplace
- **Body**: `{ "agent_id": "<uuid>", "side": "bid|ask", "capability": "<string>", "price": <int gt 0>, "quantity": <int default 1> }`
- **Response**: `OrderResponse` (status 201)

### GET /market/book/{capability}
Get the current order book for a capability
- **Response**: `OrderBookResponse` (`capability`, `bids`: list of orders, `asks`: list of orders)

### POST /market/match/{capability}
Trigger order matching for a capability (normally called by the simulator)
- **Query params**: `tick` (default 0)
- **Response**: `List[TradeResponse]`

### GET /market/trades
List recent trades
- **Query params**: `capability` (optional filter), `limit` (1–200, default 50), `offset` (default 0)
- **Response**: `List[TradeResponse]` (`id`, `bid_order_id`, `ask_order_id`, `buyer_agent_id`, `seller_agent_id`, `capability`, `price`, `status`, `latency_ms`, `tick`)

---

## Scenarios (`/scenarios`)

### GET /scenarios/
List all available simulation scenarios
- **Response**: `List[ScenarioListItem]` (`name`, `description`, `default_config`)

### POST /scenarios/start
Start a simulation with the given scenario configuration
- **Body**: `ScenarioConfig`
  - `scenario_name` (required)
  - `tick_count` (default 100)
  - `tick_interval_ms` (default 500, min 50)
  - `service_agent_count` (default 5)
  - `buyer_agent_count` (default 10)
  - `initial_balance` (default 1000)
- **Response**: `ScenarioStatus`
- **4xx** if a simulation is already running

### POST /scenarios/stop
Stop the currently running simulation
- **Response**: `ScenarioStatus`

### GET /scenarios/status
Get current simulation status
- **Response**: `ScenarioStatus` (`scenario_name`, `status`, `current_tick`, `total_ticks`, `agents_count`, `total_trades`, `total_volume`)

---

## WebSocket

### WS /ws/events
Real-time event stream from the simulator (connect to `ws://<host>/ws/events`)

**Event envelope**: `{ "event": "<type>", "data": { ... }, "timestamp": "<iso>" }`

| Event type | Emitted when |
|---|---|
| `OrderPlaced` | A new bid or ask is placed |
| `TradeMatched` | A bid and ask are matched |
| `SettlementComplete` | A trade settlement finishes (success or failure) |
| `TradeCompleted` | Full trade lifecycle complete (with latency_ms) |
| `SimulationTick` | Each simulation tick completes |
| `SimulationStarted` | Simulation begins |
| `SimulationStopped` | Simulation is stopped manually |
| `SimulationCompleted` | All ticks finished naturally |
| `SimulationError` | Unhandled error during simulation |

---

## Health

### GET /health
Health check endpoint
- **Response**: `{"status": "healthy"}`

## Authentication Methods

The API supports two authentication methods:

1. **JWT Token**: Include `Authorization: Bearer <token>` header
2. **API Key**: Include `X-API-Key: <key>` header

## Agent Manifest Format

Agents must provide a manifest following the Intuno specification:

```json
{
  "agent_id": "agent:namespace:name:version",
  "name": "Agent Name",
  "description": "Agent description",
  "version": "1.0.0",
  "endpoints": {
    "invoke": "https://example.com/invoke"
  },
  "capabilities": [{
    "id": "capability_name",
    "input_schema": {"type": "object", "properties": {...}},
    "output_schema": {"type": "object", "properties": {...}},
    "auth": {"type": "public"}
  }],
  "requires": [{"capability": "required_capability"}],
  "tags": ["tag1", "tag2"],
  "trust": {"verification": "self-signed"}
}
```
