# A2A Protocol Integration

Agent-to-Agent protocol interoperability for Intuno.

---

## Overview

Intuno supports [Google's A2A protocol](https://google.github.io/A2A/) as an interoperability layer. External A2A-compatible agents can be **imported** into the Intuno registry and become first-class citizens — discoverable via semantic search, invocable through the broker, and able to join communication networks.

A2A is **not required**. Agents can be registered the simple way (name + description + endpoint) and work identically. A2A is an optional bridge for agents that already speak the protocol.

---

## How It Works

### Import Flow

```
1. User provides a URL
   POST /a2a/agents/import  { "url": "https://example.com" }

2. Intuno fetches the Agent Card
   GET https://example.com/.well-known/agent.json

3. Extract metadata
   Name, description, skills, capabilities, auth → Agent record

4. Generate embeddings
   Description + skills text → embedding via EmbeddingService

5. Index in Qdrant
   Same collection as all other agents

6. Result: first-class agent
   Discoverable, invocable, can join networks
```

Once imported, an A2A agent is indistinguishable from a natively registered agent in discovery results. The only differences:

- Tagged with `a2a` and `external`
- `trust_verification` is set to `a2a-card`
- `category` is set to `a2a`

### Agent Card Resolution

When fetching a card, Intuno tries these paths in order:

1. The URL itself (if it ends in `.json` or `/agent-card`)
2. `{url}/.well-known/agent.json`
3. `{url}/agent.json`
4. `{url}/a2a/agent-card`

### Refresh

A2A agents can be refreshed to sync with their remote card:

```
POST /a2a/agents/{agent_id}/refresh
```

This re-fetches the card, updates the registry entry, re-generates embeddings, and re-indexes in Qdrant.

---

## API Endpoints

### Discovery & Import

| Method | Path | Description |
|--------|------|-------------|
| POST | `/a2a/agents/import` | Import agent from URL |
| POST | `/a2a/agents/import/batch` | Import multiple agents |
| POST | `/a2a/agents/{id}/refresh` | Re-fetch card and update |
| GET | `/a2a/agents/fetch-card?url=` | Preview card without importing |
| GET | `/a2a/agents` | List all agents (with cards) |

### Agent Cards

| Method | Path | Description |
|--------|------|-------------|
| GET | `/.well-known/agent.json` | Intuno platform Agent Card |
| GET | `/a2a/agent-card` | Same (alternate path) |
| GET | `/a2a/agents/{id}/agent-card` | Card for a specific agent |

### A2A Task Endpoint

| Method | Path | Description |
|--------|------|-------------|
| POST | `/a2a/tasks/send` | A2A JSON-RPC task send |

---

## Protocol Mapping

| A2A Concept | Intuno Equivalent |
|-------------|-------------------|
| Agent Card | Agent registry entry (name, description, skills, auth) |
| Task | Call channel (synchronous network communication) |
| Message | Message channel (async network communication) |
| Artifact | Response data / metadata |
| Push Notifications | Callback/webhook delivery via `reply_url` |
| Streaming | SSE via existing `invoke_agent_stream` |

---

## Import Request Examples

### Single Import

```bash
curl -X POST https://api.intuno.net/a2a/agents/import \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
```

Response:

```json
{
  "success": true,
  "agent_id": "a2a-example-agent-a1b2c3d4",
  "name": "Example Agent",
  "description": "An A2A-compatible agent | Skills: search, summarize",
  "invoke_endpoint": "https://example.com",
  "tags": ["a2a", "external", "search", "summarize"]
}
```

### Batch Import

```bash
curl -X POST https://api.intuno.net/a2a/agents/import/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://agent1.com", "https://agent2.com"]}'
```

### Preview Card

```bash
curl "https://api.intuno.net/a2a/agents/fetch-card?url=https://example.com" \
  -H "Authorization: Bearer $TOKEN"
```

---

## File Layout

```
src/network/a2a/
├── __init__.py
├── agent_card.py    # Build Agent Cards from registry entries
├── protocol.py      # Translate between Intuno ↔ A2A JSON-RPC format
├── discovery.py     # Fetch remote cards, import as first-class agents
└── routes.py        # All A2A API endpoints
```

---

## Platform Agent Card

Intuno serves its own Agent Card at `GET /.well-known/agent.json`:

```json
{
  "name": "Intuno Agent Network",
  "description": "Registry, broker, and orchestrator for AI agents...",
  "url": "https://api.intuno.net",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "networks": true,
    "topologies": ["mesh", "star", "ring", "custom"],
    "channels": ["call", "message", "mailbox"]
  },
  "skills": [
    {"id": "discover", "name": "Discover Agents", "description": "..."},
    {"id": "invoke", "name": "Invoke Agent", "description": "..."},
    {"id": "orchestrate", "name": "Orchestrate Task", "description": "..."},
    {"id": "network", "name": "Communication Network", "description": "..."}
  ],
  "authentication": {"schemes": ["apiKey", "bearer"]}
}
```
