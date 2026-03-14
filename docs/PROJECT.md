# Project Documentation

This document describes the **Wisdom** (Intuno) project: a decentralized AI agent network and its supporting applications.

---

## Overview

The project consists of three main repositories:

| Repository        | Purpose |
|-------------------|--------|
| **wisdom**        | Backend API (Intuno): registry, broker, auth, tasks (orchestrator), conversations, integrations. FastAPI + PostgreSQL + Qdrant. |
| **wisdom-frontend** | Next.js web app: landing, dashboard (agents, manifests, analytics, activity, network, settings), docs. Consumes the wisdom API. |
| **wisdom-agents** | Optional agent runtime: configurable chat agents (by name) with API-key auth. FastAPI service that can run alongside or separate from the main backend. |

Additional artifacts:

- **intuno_sdk** (inside wisdom): Python SDK for discovery and invocation; LangChain and OpenAI integrations.
- **demo** (inside wisdom): Demo agents and manifests; script to register and invoke agents.

---

## Core Concepts

- **Agent** — An AI-powered service with one or more **capabilities**. Described by a `manifest.json` (name, description, endpoints, capabilities, tags).
- **Capability** — A callable function: id, input/output schemas, auth type.
- **Registry** — Central directory: register agents, list/search (including semantic discovery via embeddings), my-agents, rate, trending, new.
- **Broker** — Proxy for agent-to-agent calls: invoke a capability on a registered agent; handles auth and invocation logging.
- **Task (Orchestrator)** — High-level “goal + input” API: the server plans steps, discovers agents, invokes via the broker, and returns a result (sync or async with polling).
- **Conversation / Message** — Conversation threads and messages; creation is tied to broker/orchestrator usage; API is read/update/delete and logs.

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────────────────────────────────┐
│  wisdom-frontend    │     │  wisdom (Intuno backend)                          │
│  (Next.js)          │────▶│  • Auth (JWT, API keys)                            │
│  • Landing / Login  │     │  • Registry (agents, discover, my-agents, rate)   │
│  • Dashboard        │     │  • Broker (invoke, logs)                           │
│  • Agents / Manifests│    │  • Tasks (orchestrator: plan → discover → invoke)  │
│  • Analytics / etc. │     │  • Conversations & Messages                       │
└─────────────────────┘     │  • Integrations, Brands, Invocation logs          │
                            │  • PostgreSQL, Qdrant (embeddings)                │
                            └──────────────────────────────────────────────────┘
                                                      │
                                                      │ invoke
                                                      ▼
                            ┌──────────────────────────────────────────────────┐
                            │  Registered agents (external or wisdom-agents)   │
                            │  e.g. demo agents on 8001, 8002, 8003             │
                            └──────────────────────────────────────────────────┘

┌─────────────────────┐
│  wisdom-agents      │  Optional: configurable chat agents (POST /agents/{name})
│  (FastAPI, port     │  API-key auth; used for “chat with agent by name” flows.
│  8001 by default)   │  Separate deploy; not required for registry/broker/tasks.
└─────────────────────┘
```

- **wisdom-frontend** talks to **wisdom** via `NEXT_PUBLIC_API_URL` (default `http://localhost:8000/`), using JWT in `Authorization: Bearer <token>` and `lib/api-client.ts` + `lib/api/*.ts`.
- **wisdom** uses **PostgreSQL** (with optional pgvector), **Qdrant** for semantic search, and **OpenAI** for embeddings (and optional LLM enhancement/planner).
- **Tasks** are authenticated with **API key** (header); other APIs use **JWT** or **API key** as configured.

---

## Repository: wisdom (backend)

- **Stack:** Python 3.12+, FastAPI, SQLAlchemy, asyncpg, Pydantic, Alembic, Qdrant, OpenAI.
- **Layout:** `src/` — `routes/`, `services/`, `repositories/`, `models/`, `schemas/`, `core/` (auth, security, settings), `utilities/` (planner, executor, orchestrator, embedding, qdrant_service, etc.).
- **Entry:** `uvicorn src.main:app --reload` → API at `http://localhost:8000`; OpenAPI at `/docs`.
- **Config:** `src/core/settings.py` (Pydantic Settings): `DATABASE_URL`, `OPENAI_API_KEY`, `JWT_SECRET_KEY`, `QDRANT_URL`, `ENABLE_LLM_ENHANCEMENT`, `PLANNER_USE_LLM`, `TASK_TIMEOUT_SECONDS`, etc. Env file: `.env`.

### Main API areas

- **Auth:** register, login, API keys (create/list/delete), me.
- **Registry:** register/update/delete agents, list/search, discover (semantic), my-agents, new, trending, rate, get by id.
- **Broker:** invoke, logs (global and per-agent).
- **Tasks:** POST /tasks (goal + input; optional idempotency, async), GET /tasks/{task_id}.
- **Conversations:** list, get, update, delete, logs, message list.
- **Messages:** get, delete.
- **Integrations / Brands / Invocation log:** CRUD and helpers as per routes.
- **Health:** GET /health.

Detailed endpoint list: [API_ENDPOINTS.md](./API_ENDPOINTS.md). Deeper design: [ORCHESTRATOR.md](./ORCHESTRATOR.md), [HOW_EMBEDDING_SYSTEM_WORKS.md](./HOW_EMBEDDING_SYSTEM_WORKS.md), [SYNC.md](./SYNC.md), [TOOL_CALL_GUIDE.md](./TOOL_CALL_GUIDE.md).

### Demo and SDK

- **Demo:** `demo/` — `demo.py`, `agents/*.py`, `manifests/*.json`; see `demo/README.md`. Registers and invokes sample agents; main server must be running.
- **SDK:** `intuno_sdk/` — Python client (sync/async), discover + invoke; LangChain/OpenAI integrations; see `intuno_sdk/README.md`.
- **Static demo UI:** Served at `/demo` when `static/demo` exists.

---

## Repository: wisdom-frontend

- **Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS, Radix UI, shadcn-style components.
- **Layout:** `app/` — (landing), login, signup, dashboard (agents, manifests, analytics, activity, network, settings), docs; `components/`, `lib/`, `hooks/`, `context/`, `sections/`, `types/`.
- **API client:** `lib/api-client.ts` (base URL, JWT in localStorage, `getApiUrl`, `getStoredToken`, etc.); `lib/api/request.ts` (`apiRequest`); `lib/api/auth.ts`, `lib/api/registry.ts`, `lib/api/broker.ts`.
- **Env:** `NEXT_PUBLIC_API_URL` for backend (default `http://localhost:8000/`).
- **Commands:** `npm run dev`, `npm run build`, `npm run start`.

---

## Repository: wisdom-agents

- **Stack:** Python, FastAPI, SQLAlchemy, Alembic.
- **Purpose:** Configurable chat agents: list configs, create config, chat with an agent by name (POST `/agents/{agent_name}` with messages). API-key protected.
- **Layout:** `agents/` — `main.py`, `routes/` (health, agent_config), `services/`, `repositories/`, `models/`, `schemas/`, `core/` (e.g. auth), `database.py`, `utilities/`.
- **Entry:** e.g. `uvicorn` on port 8001 (see `agents/main.py`). Independent from the wisdom backend; can be used by frontends or other services that need “chat with agent X” without going through the main registry/broker.

---

## Agent manifest format

Agents register with the registry using a manifest. Minimal structure:

```json
{
  "agent_id": "agent:namespace:name:version",
  "name": "Agent Name",
  "description": "Agent description",
  "version": "1.0.0",
  "endpoints": { "invoke": "https://example.com/invoke" },
  "capabilities": [{
    "id": "capability_name",
    "input_schema": { "type": "object", "properties": { ... } },
    "output_schema": { "type": "object", "properties": { ... } },
    "auth_type": { "type": "public" }
  }],
  "tags": ["tag1", "tag2"],
  "trust": { "verification": "self-signed" }
}
```

Example manifests: `demo/manifests/*.json`.

---

## Getting started (local)

1. **Backend (wisdom)**  
   - Clone wisdom, create venv, install deps (e.g. `uv` or `pip` from pyproject.toml).  
   - Run PostgreSQL (and optionally Qdrant) e.g. via Docker.  
   - Set `.env` (e.g. `DATABASE_URL`, `OPENAI_API_KEY`, `JWT_SECRET_KEY`, `QDRANT_URL`).  
   - `alembic upgrade head`  
   - `uvicorn src.main:app --reload` → `http://localhost:8000`

2. **Frontend (wisdom-frontend)**  
   - Clone wisdom-frontend, `npm install`.  
   - Set `NEXT_PUBLIC_API_URL` if backend is not at `http://localhost:8000/`.  
   - `npm run dev`

3. **Agents (optional)**  
   - Run demo agents (see `demo/README.md`) or wisdom-agents: e.g. `uvicorn agents.main:app --reload --port 8001`.

4. **Docs**  
   - API reference: `http://localhost:8000/docs`  
   - Project and design: this file and the other docs in `docs/`.

---

## Documentation index (wisdom repo)

| Document | Description |
|----------|-------------|
| [PROJECT.md](./PROJECT.md) | This file — project overview and repo layout. |
| [API_ENDPOINTS.md](./API_ENDPOINTS.md) | List of API endpoints and auth. |
| [ORCHESTRATOR.md](./ORCHESTRATOR.md) | Task/orchestrator design and execution model. |
| [HOW_EMBEDDING_SYSTEM_WORKS.md](./HOW_EMBEDDING_SYSTEM_WORKS.md) | Embedding and semantic search. |
| [SYNC.md](./SYNC.md) | Sync/async and polling behavior. |
| [TOOL_CALL_GUIDE.md](./TOOL_CALL_GUIDE.md) | Tool-call integration guide. |
| [AGENT_REGISTRATION_SUMMARY.md](./AGENT_REGISTRATION_SUMMARY.md) | Agent registration summary. |
| [DEMO_README.md](./DEMO_README.md) | Demo usage (duplicate/summary of `demo/README.md`). |
