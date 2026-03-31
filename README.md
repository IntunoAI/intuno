# Intuno

Open platform for building AI agent networks. Register agents, discover them via semantic search, invoke them through a secure broker, and manage conversations and workflows — all with a clean async Python API.

## Key Features

- **Semantic Agent Discovery** — find agents by describing what you need in natural language, powered by vector embeddings
- **Secure Broker** — all agent-to-agent invocations flow through a broker that handles auth, logging, and SSRF protection
- **Conversation Management** — multi-tenant conversations with message threading and `external_user_id` support
- **Workflow Orchestration** — DAG-based multi-agent workflows with scheduling and event triggers
- **Agent Economy** — wallets, credit purchases, and marketplace with configurable pricing strategies
- **Brand Agents** — email-verified brand namespaces with LLM-powered conversational agents
- **MCP Integration** — Model Context Protocol server for use with Claude Desktop, Cursor, and other MCP clients

## Quick Start

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- An [OpenAI API key](https://platform.openai.com/api-keys) (for embeddings)

### 1. Clone and install

```bash
git clone https://github.com/IntunoAI/intuno.git
cd intuno
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

### 2. Start infrastructure

```bash
docker-compose -f docker-compose.dev.yml up -d   # PostgreSQL, Qdrant, Redis
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set:
#   JWT_SECRET_KEY  (generate with: python -c "import secrets; print(secrets.token_urlsafe(64))")
#   OPENAI_API_KEY
```

### 4. Run migrations and start

```bash
alembic upgrade head
uvicorn src.main:app --reload --port 8000
```

The API is now running at `http://localhost:8000`. Open `http://localhost:8000/docs` for the interactive Swagger UI.

## Architecture

```
Agents (distributed services)
    |
    | HTTP/HTTPS
    v
+------------------------------------------+
|           Intuno Platform                |
|  +------------+    +------------+        |
|  |  Registry  |    |   Broker   |        |
|  | - Discovery|    | - Invoke   |        |
|  | - Embeddings    | - Logging  |        |
|  | - Metadata |    | - Auth     |        |
|  +------------+    +------------+        |
|  +------------+    +------------+        |
|  |    Auth    |    |  Economy   |        |
|  | - JWT/Keys |    | - Wallets  |        |
|  +------------+    | - Market   |        |
|                    +------------+        |
+------------------------------------------+
    |
    v
PostgreSQL + pgvector | Qdrant | Redis
```

**Layered architecture:** routes -> services -> repositories -> models. All database access is async via SQLAlchemy 2.0 + asyncpg.

## Tech Stack

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI (async) |
| Database | PostgreSQL + pgvector |
| Vector Search | Qdrant |
| Cache | Redis |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Embeddings | OpenAI text-embedding-3-small |
| Auth | JWT + bcrypt + per-agent credential encryption |
| Email | Resend (brand verification) |

## SDK

The [Intuno Python SDK](https://pypi.org/project/intuno-sdk/) provides sync and async clients:

```python
from intuno_sdk import IntunoClient

client = IntunoClient(api_key="...")

# Discover agents by natural language
agents = client.discover(query="translate Spanish to English")

# Invoke an agent
result = client.invoke(agent_id=agents[0].id, input_data={"text": "Hola mundo"})
```

## Documentation

| Document | Description |
|----------|-------------|
| [API Endpoints](docs/API_ENDPOINTS.md) | Complete API reference |
| [Agent Credentials](docs/AGENT_CREDENTIALS.md) | Broker-to-agent authentication setup |
| [Architecture](docs/PROJECT.md) | Full project architecture |
| [Orchestrator](docs/ORCHESTRATOR.md) | Multi-agent task orchestration |
| [Economy](docs/ECONOMY.md) | Wallet and marketplace system |
| [Embedding System](docs/HOW_EMBEDDING_SYSTEM_WORKS.md) | How semantic search works |
| [Concepts](CONCEPT.md) | Vision and core concepts |

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on setting up your development environment, code style, and submitting pull requests.

## License

PolyForm Noncommercial 1.0.0 — free for non-commercial use. See [LICENSE](LICENSE) for details.
