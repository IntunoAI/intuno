# wisdom

Core platform backend for the Intuno Agent Network. Handles agent registry, semantic discovery, broker (agent-to-agent invocation), auth, conversations, tasks, brand agents, and analytics.

## Tech Stack
- Python 3.12+ / FastAPI (async)
- PostgreSQL + pgvector (asyncpg driver)
- Qdrant — vector database for semantic search
- Redis — caching
- SQLAlchemy 2.0 (async ORM) + Alembic
- OpenAI API — embeddings and LLM planning
- Resend — transactional email (brand verification)
- JWT (python-jose) + bcrypt — auth
- uvicorn — ASGI server

## Project Structure
```
src/
├── main.py                  # FastAPI app, router registration, MCP mount
├── database.py              # Async session factory
├── core/
│   ├── settings.py          # Pydantic Settings (env vars)
│   ├── auth.py              # JWT generation/validation
│   ├── security.py          # Password hashing
│   ├── credential_crypto.py # Per-agent encrypted credentials
│   └── redis_client.py      # Redis connection
├── models/                  # SQLAlchemy ORM models
├── schemas/                 # Pydantic request/response schemas
├── repositories/            # DB access layer (one file per domain)
├── services/                # Business logic (one file per domain)
├── routes/                  # FastAPI routers (registry, broker, auth, brand, etc.)
└── utilities/
    ├── embedding.py         # OpenAI text-embedding-3-small
    ├── qdrant_service.py    # Vector upsert/search
    ├── orchestrator.py      # Multi-agent DAG execution
    ├── planner.py           # LLM-based task decomposition
    ├── executor.py          # Step execution
    └── brand_agent_llm.py   # Brand agent chat completions
economy/
├── models/                  # Wallet, Transaction, Order, Trade, CreditPurchase ORM models
├── schemas/                 # Pydantic request/response schemas
├── repositories/            # wallets, market, purchases, agents
├── services/                # wallets, market, purchases, scenarios, agents
├── routes/                  # /wallets, /market, /credits, /scenarios, WebSocket
│                            # Note: routes/agents.py exists but is NOT mounted in main.py
└── utilities/
    ├── pricing.py           # Fixed, Dynamic, Auction pricing strategies
    ├── settlement.py        # Double-entry trade settlement (95% success rate)
    ├── simulator.py         # Tick-based simulation loop
    ├── event_bus.py         # In-memory pub/sub → WebSocket broadcast
    ├── scenarios.py         # Hardcoded scenario definitions
    └── agent_behaviors/     # BuyerAgent, ServiceAgent, Arbitrageur
```

## Local Development
```bash
# Start infrastructure
docker-compose -f docker-compose.dev.yml up -d  # PostgreSQL, Qdrant, Redis

# Install dependencies
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run migrations
alembic upgrade head

# Start server (hot-reload)
uvicorn src.main:app --reload --port 8000
# Swagger UI: http://localhost:8000/docs
```

## Database Migrations
```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "describe the change"

# Apply
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Key Patterns
- **Layered architecture:** routes → services → repositories → models. Don't skip layers.
- **Async throughout:** all DB calls use `async with get_session() as session`. Never use sync SQLAlchemy session.
- **Semantic search:** embeddings are stored in Qdrant (not Postgres). Use `qdrant_service.py` for vector ops.
- **Broker pattern:** all agent-to-agent invocations flow through the broker route for security and logging.
- **Credential encryption:** agent API keys are encrypted at rest using `credential_crypto.py` — never store them in plaintext.
- **Brand agents:** have their own email verification flow via Resend. See `routes/brand.py` and `services/brand.py`.
- **MCP:** mounted at `/mcp` via `mcp_app.py`. Changes to MCP tools require a server restart.
- **Economy — double-entry bookkeeping:** all transfers use `atomic_debit()` / `atomic_credit()` with a shared `reference_id`; transaction records are immutable.

## Environment Variables (required)
See `src/core/settings.py` for the full list. Key ones:
- `DATABASE_URL` — postgres+asyncpg connection string
- `QDRANT_URL`, `QDRANT_API_KEY`
- `REDIS_URL`
- `OPENAI_API_KEY`
- `JWT_SECRET_KEY`
- `RESEND_API_KEY` — for brand verification emails
- `ECONOMY_CREDIT_PACKAGES` — JSON array defining available credit packages (id, credits, price_cents, label)

## Testing
```bash
pytest tests/ -v
```
Tests use an in-process test client with a separate test database. Migrations must be up-to-date before running tests.
