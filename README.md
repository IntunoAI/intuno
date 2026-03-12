# Intuno - The Decentralized Agent Network

Intuno is a network designed to connect and empower AI agents. It provides the infrastructure for agents to register their capabilities, discover other agents, and invoke them in a seamless and secure manner. Our goal is to foster a collaborative ecosystem where developers can share and monetize their agents' unique abilities.

This project is built on the idea that the future of AI is not monolithic, but a rich network of specialized agents that can work together to solve complex problems. By providing the "plumbing" for this network, we hope to unlock a new wave of innovation in the AI space.

## Core Concepts

- **Agent:** An AI-powered service that can perform one or more `Capabilities`. Each agent is defined by a `manifest.json` file that describes its name, description, and capabilities.
- **Capability:** A specific function that an agent can perform. It is defined by a name, description, and a set of input and output schemas.
- **Registry:** The central directory of the network. Agents are registered with the registry, which stores their manifests and makes them discoverable to other agents. The registry supports both simple and semantic search to find agents based on their capabilities.
- **Broker:** The proxy for all agent-to-agent communication. When one agent wants to invoke another, it sends a request to the broker, which then forwards the request to the target agent. The broker handles authentication, logging, and other cross-cutting concerns.

## Getting Started

To get the Intuno network running locally, follow these steps:

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/artugrob/intuno.git
    cd intuno
    ```

2.  **Set up the environment:**
    This project uses `uv` for package management.
    ```bash
    uv venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    ```

3.  **Run the database:**
    The project uses Docker to run a PostgreSQL database with the `pgvector` extension.
    ```bash
    docker-compose up -d
    ```

4.  **Run the migrations:**
    ```bash
    alembic upgrade head
    ```

5.  **Start the server:**
    ```bash
    uvicorn src.main:app --reload
    ```
    The API will be available at `http://localhost:8000`.

## API Overview

The Intuno API is divided into three main parts:

- **Auth:** Handles user and agent authentication.
- **Registry:** Manages the registration and discovery of agents.
- **Broker:** Proxies requests between agents.

For a detailed list of endpoints, please refer to the [API_ENDPOINTS.md](docs/API_ENDPOINTS.md) file or the OpenAPI documentation at `http://localhost:8000/docs`.

## Agent Credentials (Broker-to-Agent Auth)

When the broker invokes an agent, it sends the agent's credential (API key or bearer token) in the request. You configure this per agent via `POST /registry/agents/{uuid}/credentials`.

### Example: API key with default header (X-API-Key)

Most agents expect the key in the `X-API-Key` header:

```bash
curl -X POST "http://localhost:8000/registry/agents/{agent_uuid}/credentials" \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"credential_type": "api_key", "value": "your-secret-key"}'
```

### Example: Custom header name (e.g. X-Auth-Token)

If your agent server uses a different header:

```bash
curl -X POST "http://localhost:8000/registry/agents/{agent_uuid}/credentials" \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_type": "api_key",
    "value": "your-secret-key",
    "auth_header": "X-Auth-Token"
  }'
```

### Example: Bearer token (Authorization header)

For OAuth2/JWT-style auth:

```bash
curl -X POST "http://localhost:8000/registry/agents/{agent_uuid}/credentials" \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_type": "bearer_token",
    "value": "eyJhbGciOiJIUzI1NiIs...",
    "auth_header": "Authorization",
    "auth_scheme": "Bearer"
  }'
```

This sends `Authorization: Bearer eyJhbGciOiJIUzI1NiIs...` to the agent.

### Bulk inject (scripts)

For local development with wisdom-agents, use the inject script to set credentials for all agents:

```bash
# From wisdom-agents .env
export AGENTS_API_KEY=$(grep '^AGENTS_API_KEY=' ../wisdom-agents/.env | cut -d= -f2- | tr -d '"')
python scripts/inject_agent_credentials.py

# With custom header
python scripts/inject_agent_credentials.py --api-key "key" --header "X-Auth-Token"
```

---

**Full project documentation** (architecture, all repos, getting started): [docs/PROJECT.md](docs/PROJECT.md).
