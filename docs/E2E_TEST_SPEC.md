# E2E Test Specification

End-to-end testing strategy for Intuno communication networks using real agent implementations.

---

## Architecture Decision

**E2E tests live in the agents repo, not here.**

- E2E tests *are* agent code that consumes Intuno — they belong on the consumer side
- The agents repo already has real agent implementations
- The agents repo gets its own CI pipeline testing against staging Intuno 24/7
- Intuno repo keeps unit tests (63) and integration tests (`test_networks.py`) — no dependency on external agent processes
- Agent implementations can evolve without touching Intuno's CI

**This document is the contract.** It specifies what agent types and test scenarios the agents repo should implement.

---

## Reference Agents

Five agent types are needed to cover all communication patterns.

### Agent 1: Echo Agent

The simplest possible agent. Receives any message, returns it with `[ECHO] ` prefix.

**Capabilities:**
- Webhook-based (`callback_url`)
- Handles all three channels (call, message, mailbox via polling)
- For calls: returns `{"echo": "[ECHO] <content>"}`
- For messages: POSTs to `reply_url` with `[ECHO] <content>`

**What it tests:**
- Basic webhook delivery (Intuno → agent)
- `reply_url` mechanics (agent → Intuno)
- Call response semantics (synchronous blocking)
- Delivery payload structure validation
- Context presence in deliveries
- Signed URL acceptance

**Implementation sketch:**

```python
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

@app.post("/webhook")
async def echo(request: Request):
    payload = await request.json()
    echo_content = f"[ECHO] {payload['content']}"

    if payload["channel"] == "call":
        return {"echo": echo_content}

    # For messages: reply via signed callback URL
    async with httpx.AsyncClient() as client:
        await client.post(payload["reply_url"], json={
            "content": echo_content,
            "recipient_participant_id": payload["sender"]["participant_id"],
            "channel_type": "message",
        })
    return {"status": "ok"}
```

---

### Agent 2: Conversational Agent

Maintains conversation state using the `context[]` from delivery payloads. Responds contextually, referencing previous messages.

**Capabilities:**
- Webhook-based
- Uses the `context` array to build conversation history
- References previous speakers and topics in responses
- Tracks how many messages it has exchanged (via context length)

**What it tests:**
- Context window accuracy (are all messages present?)
- Multi-turn conversation coherence
- Message ordering in context
- Context growth over multiple exchanges
- `message_id` presence in context entries

**Implementation sketch:**

```python
@app.post("/webhook")
async def conversational(request: Request):
    payload = await request.json()

    # Build a response that proves we have context
    context = payload.get("context", [])
    context_summary = f"I see {len(context)} messages in history."
    if context:
        first = context[0]
        context_summary += f" First message was from {first['sender']}."

    response = f"Message #{len(context) + 1}: {context_summary} Responding to: {payload['content'][:50]}"

    if payload["channel"] == "call":
        return {"response": response, "context_size": len(context)}

    async with httpx.AsyncClient() as client:
        await client.post(payload["reply_url"], json={
            "content": response,
            "recipient_participant_id": payload["sender"]["participant_id"],
            "channel_type": "message",
        })
    return {"status": "ok"}
```

---

### Agent 3: Proactive Agent

On receiving any message, proactively messages ALL other participants visible in `network_participants[]`.

**Capabilities:**
- Webhook-based
- Reads `network_participants` to discover all peers
- Sends individual messages to every other participant
- Can be used as a star hub or broadcast coordinator

**What it tests:**
- Proactive communication (agent-initiated, not just responses)
- Multi-directional message flow (fan-out to multiple recipients)
- Topology enforcement (should fail in star if not hub, should fail in ring if targets wrong peer)
- `network_participants` field accuracy

**Implementation sketch:**

```python
@app.post("/webhook")
async def proactive(request: Request):
    payload = await request.json()
    my_name = "Proactive Agent"  # Must match participant name

    if payload["channel"] == "call":
        return {"response": "acknowledged"}

    participants = payload.get("network_participants", [])
    my_id = next(
        (p["participant_id"] for p in participants if p["name"] == my_name),
        None,
    )

    async with httpx.AsyncClient() as client:
        for p in participants:
            if p["participant_id"] == my_id:
                continue
            await client.post(payload["reply_url"], json={
                "content": f"Proactive message to {p['name']}: I received '{payload['content'][:30]}...'",
                "recipient_participant_id": p["participant_id"],
                "channel_type": "message",
            })

    return {"status": "ok"}
```

---

### Agent 4: Polling Agent

No webhook endpoint. Uses `polling_enabled: true` and checks its inbox on a timer.

**Capabilities:**
- No `callback_url` — polling only
- Background loop: poll inbox → process → ack → reply via API
- Can handle mailbox channel messages

**What it tests:**
- Inbox polling flow (`GET /inbox/{pid}`)
- Message acknowledgment (`POST /messages/ack`)
- Mailbox channel (no push delivery)
- Reply via API (not via `reply_url`)
- Unread-only filtering (acknowledged messages don't reappear)

**Implementation sketch:**

```python
import asyncio
import httpx

BASE = "https://api.intuno.net"

async def polling_loop(network_id: str, participant_id: str, token: str):
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"{BASE}/networks/{network_id}/inbox/{participant_id}",
                headers=headers,
                params={"limit": 50},
            )
            messages = resp.json()

            if messages:
                msg_ids = []
                for msg in messages:
                    # Reply via API
                    await client.post(
                        f"{BASE}/networks/{network_id}/messages/send",
                        headers=headers,
                        json={
                            "sender_participant_id": participant_id,
                            "recipient_participant_id": msg["sender_participant_id"],
                            "content": f"[POLL] Received: {msg['content'][:80]}",
                        },
                    )
                    msg_ids.append(msg["id"])

                # Acknowledge all processed messages
                await client.post(
                    f"{BASE}/networks/{network_id}/messages/ack",
                    headers=headers,
                    json={"message_ids": msg_ids},
                )

            await asyncio.sleep(3)
```

---

### Agent 5: Multi-Channel Agent

Handles all three channels, responding differently based on channel type.

**Capabilities:**
- Webhook-based + polling
- Different behavior per channel:
  - `call` → returns structured JSON immediately
  - `message` → replies via `reply_url` with acknowledgment
  - `mailbox` → processes via polling, replies via API

**What it tests:**
- Channel-specific routing within a single agent
- Mixed channel workflows in the same network
- Call blocking semantics (30s timeout)
- Message/mailbox distinction

**Implementation sketch:**

```python
@app.post("/webhook")
async def multi_channel(request: Request):
    payload = await request.json()
    channel = payload["channel"]

    if channel == "call":
        return {
            "channel_received": "call",
            "response": f"Sync response to: {payload['content'][:50]}",
            "processed_at": datetime.utcnow().isoformat(),
        }

    if channel == "message":
        async with httpx.AsyncClient() as client:
            await client.post(payload["reply_url"], json={
                "content": f"[MSG ACK] Received via message channel: {payload['content'][:50]}",
                "recipient_participant_id": payload["sender"]["participant_id"],
                "channel_type": "message",
            })

    # Mailbox messages: no immediate response (processed via polling)
    return {"status": "ok", "channel_received": channel}
```

---

## E2E Test Scenarios

### Scenario 1: Basic Echo Round-Trip

**Agents:** Echo + API caller (test script)
**Network:** mesh

```
Test script → POST /messages/send (to Echo)
  → Intuno delivers to Echo's webhook
  → Echo POSTs to reply_url with [ECHO] prefix
  → Test script polls /inbox and finds Echo's reply
```

**Assertions:**
- Original message appears in `/messages` list
- Echo's reply appears in caller's inbox
- Reply content starts with `[ECHO] `
- Both messages appear in `/context` with correct senders
- Context entry includes `message_id`

---

### Scenario 2: Multi-Turn Conversation

**Agents:** Conversational x 2
**Network:** mesh

```
Agent A receives trigger via API
  → A messages B (via /messages/send)
  → B receives with context, replies referencing context
  → A receives B's reply with updated context
  → Repeat for 5 turns
```

**Assertions:**
- Context grows with each exchange (1, 2, 3, 4, 5... messages)
- Each agent sees the full conversation in `context[]`
- Messages are ordered chronologically
- `context_size` in responses matches expected count
- All `message_id` fields are present and unique

---

### Scenario 3: Proactive Initiation

**Agents:** Proactive + Echo
**Network:** mesh

```
Test script sends one message to Proactive
  → Proactive receives and messages Echo (proactively)
  → Echo replies to Proactive
  → Test script verifies 3 messages in context (trigger, proactive, echo reply)
```

**Assertions:**
- Proactive agent successfully sends without being the original recipient
- Echo receives the proactive message
- Context shows messages from 3 different senders (test, proactive, echo)
- `in_reply_to_id` is null on the proactive message (new conversation)

---

### Scenario 4: Star Topology Hub-Spoke

**Agents:** Proactive (as hub) + Echo x 2 (as spokes)
**Network:** star

```
Hub sends to Spoke A → succeeds
Hub sends to Spoke B → succeeds
Spoke A tries to send to Spoke B → 400 (topology violation)
Spoke A sends to Hub → succeeds (reply to hub)
```

**Assertions:**
- Hub (first participant) can message any spoke
- Spoke-to-spoke communication is blocked with 400
- Spokes can reply to hub via `reply_url`
- Error message mentions "hub"

---

### Scenario 5: Ring Topology Chain

**Agents:** Echo x 3 (A, B, C)
**Network:** ring

```
A → B → C → A (each forwards to next)
A ✗→ C (skip B, should fail with 400)
```

**Assertions:**
- A can send to B (next in order)
- B can send to C (next in order)
- C can send to A (wraps around)
- A cannot send to C (skipping B) — returns 400
- Error message mentions "Ring topology"

---

### Scenario 6: Polling Workflow

**Agents:** Polling + Echo
**Network:** mesh

```
Test script sends message via /mailbox to Polling Agent
  → Polling Agent polls /inbox and finds it
  → Polling Agent acks the message
  → Polling Agent replies via /messages/send
  → Verify acked messages don't reappear in inbox
```

**Assertions:**
- Mailbox message appears in inbox
- After ack, message does not appear in next inbox poll
- Polling agent can reply via API (not reply_url)
- Both messages appear in context

---

### Scenario 7: Mixed Channels

**Agents:** Multi-Channel x 2
**Network:** mesh

```
Agent A calls Agent B (synchronous) → gets immediate response
Agent A messages Agent B (async) → B replies via reply_url
Agent A sends to B's mailbox → B polls and processes
```

**Assertions:**
- Call returns synchronous response within timeout
- Message delivery triggers webhook
- Mailbox message only appears via inbox polling
- All three channel types recorded in context with correct `channel` field
- Context entries distinguish between "call", "message", "mailbox"

---

### Scenario 8: Delivery Retry

**Agents:** Echo (starts offline, comes online after 5s)
**Network:** mesh

```
Send message to Echo while it's offline
  → Delivery fails → enqueued for retry
  → Echo comes online after 5s
  → Delivery worker retries → succeeds
```

**Assertions:**
- Message status is `pending` initially
- After retry succeeds, message status becomes `delivered`
- Echo receives the message (eventually)
- No duplicate deliveries

**Note:** This test requires the ability to start/stop the Echo agent process.

---

### Scenario 9: 5-Agent Mesh Conversation

**Agents:** Conversational x 5
**Network:** mesh

```
A → B, B → C, C → D, D → E, E → A
  → Verify all 5 messages in context
  → Send 5 more (A → C, B → D, C → E, D → A, E → B)
  → Verify context has 10 messages, all senders present
```

**Assertions:**
- Context grows correctly with many participants
- All 5 participant names appear in context
- `network_participants` in deliveries lists all 5
- No message loss at scale
- Context window limits respected (max 30 in deliveries)

---

### Scenario 10: Cross-Network Isolation

**Agents:** Echo x 2 in Network A, Echo x 2 in Network B
**Networks:** mesh x 2

```
Send messages in Network A
Send messages in Network B
  → Verify Network A context has only Network A messages
  → Verify Network B context has only Network B messages
```

**Assertions:**
- Messages don't leak between networks
- Context is network-scoped
- Same agent can participate in multiple networks independently

---

### Scenario 11: Participant Lifecycle

**Agents:** Echo x 3 (A, B, C)
**Network:** mesh

```
A, B, C join and exchange messages
  → Remove B (DELETE /participants/{B_id})
  → A sends to C → succeeds
  → A sends to B → fails (participant removed)
  → Verify B's old messages still in context
  → Add D as replacement → communication resumes
```

**Assertions:**
- Removed participant cannot receive new messages
- Sending to removed participant returns 400
- Historical messages from removed participant persist in context
- New participant can see old context after joining

---

### Scenario 12: A2A Interop

**Agents:** A2A-compatible agent (serves `/.well-known/agent.json`)
**Network:** mesh

```
Import A2A agent: POST /a2a/agents/import {"url": "..."}
  → Verify agent appears in registry
  → Add imported agent to a network
  → Send message via A2A tasks/send endpoint
  → Verify response in A2A JSON-RPC format
```

**Assertions:**
- Agent Card is fetched successfully
- Agent is indexed in registry with `a2a` tag
- A2A task send produces valid JSON-RPC response
- Agent can participate in normal network communication

---

## 24/7 Monitoring Strategy

### Architecture

```
Agents Repo
├── agents/
│   ├── echo_agent.py
│   ├── conversational_agent.py
│   ├── proactive_agent.py
│   ├── polling_agent.py
│   └── multi_channel_agent.py
├── tests/
│   ├── e2e/
│   │   ├── conftest.py              # Fixtures: auth, network setup, cleanup
│   │   ├── test_echo_roundtrip.py   # Scenario 1
│   │   ├── test_multi_turn.py       # Scenario 2
│   │   ├── test_proactive.py        # Scenario 3
│   │   ├── test_topology_star.py    # Scenario 4
│   │   ├── test_topology_ring.py    # Scenario 5
│   │   ├── test_polling.py          # Scenario 6
│   │   ├── test_mixed_channels.py   # Scenario 7
│   │   ├── test_delivery_retry.py   # Scenario 8
│   │   ├── test_scale_mesh.py       # Scenario 9
│   │   ├── test_isolation.py        # Scenario 10
│   │   ├── test_lifecycle.py        # Scenario 11
│   │   └── test_a2a.py              # Scenario 12
│   └── health/
│       └── smoke.py                 # Quick 30-second health check
├── docker-compose.yml               # Brings up Intuno + all agents
└── .github/workflows/
    ├── e2e.yml                       # Full suite (hourly)
    └── health.yml                    # Smoke test (every 5 minutes)
```

### Health Check (Every 5 Minutes)

A quick smoke test that validates the core path:

```python
async def health_check():
    """30-second smoke test. Create network → send message → verify → cleanup."""
    token = await login()

    # Create network
    network = await create_network(token, "health-check")

    # Add 2 polling participants
    alice = await join_network(token, network["id"], "Alice", polling=True)
    bob = await join_network(token, network["id"], "Bob", polling=True)

    # Send message Alice → Bob
    await send_message(token, network["id"], alice["id"], bob["id"], "health ping")

    # Verify Bob's inbox
    inbox = await get_inbox(token, network["id"], bob["id"])
    assert len(inbox) >= 1
    assert "health ping" in inbox[0]["content"]

    # Verify context
    context = await get_context(token, network["id"])
    assert len(context["entries"]) >= 1

    # Cleanup
    await delete_network(token, network["id"])
```

### Full E2E Suite (Hourly)

Run all 12 scenarios against the live platform:

```yaml
# .github/workflows/e2e.yml
name: E2E Tests
on:
  schedule:
    - cron: '0 * * * *'  # Every hour
  workflow_dispatch: {}

jobs:
  e2e:
    runs-on: ubuntu-latest
    services:
      # Agents run as sidecar containers
      echo-agent:
        image: your-registry/echo-agent:latest
        ports: ['8001:8000']
      conversational-agent:
        image: your-registry/conversational-agent:latest
        ports: ['8002:8000']
      proactive-agent:
        image: your-registry/proactive-agent:latest
        ports: ['8003:8000']
      multi-channel-agent:
        image: your-registry/multi-channel-agent:latest
        ports: ['8004:8000']

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -e ".[test]"
      - run: pytest tests/e2e/ -v --tb=short
        env:
          INTUNO_BASE_URL: ${{ secrets.STAGING_URL }}
          INTUNO_EMAIL: ${{ secrets.E2E_EMAIL }}
          INTUNO_PASSWORD: ${{ secrets.E2E_PASSWORD }}
          ECHO_AGENT_URL: http://echo-agent:8000
          CONVERSATIONAL_AGENT_URL: http://conversational-agent:8000
          PROACTIVE_AGENT_URL: http://proactive-agent:8000
          MULTI_CHANNEL_AGENT_URL: http://multi-channel-agent:8000
```

### Critical Path Tests (Every 15 Minutes)

Run scenarios 1, 2, and 3 more frequently since they cover the core communication loop:

```yaml
name: Critical Path
on:
  schedule:
    - cron: '*/15 * * * *'

jobs:
  critical:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[test]"
      - run: pytest tests/e2e/test_echo_roundtrip.py tests/e2e/test_multi_turn.py tests/e2e/test_proactive.py -v
```

### Alerting

- **On failure**: Retry once before alerting (avoid false positives from transient network issues)
- **Alert channels**: Slack webhook + email
- **Include**: Test name, failure message, timestamp, link to run
- **Track metrics**: Latency per scenario, delivery success rate, context accuracy, over time

### Local Development

Docker Compose for running the full stack locally:

```yaml
# docker-compose.yml (in agents repo)
services:
  # Intuno platform
  intuno:
    build: ../intuno
    ports: ['8000:8000']
    depends_on: [postgres, redis, qdrant]
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@postgres:5432/intuno
      REDIS_URL: redis://redis:6379/0
      QDRANT_URL: http://qdrant:6333

  # Infrastructure
  postgres:
    image: pgvector/pgvector:pg16
    environment: { POSTGRES_DB: intuno, POSTGRES_PASSWORD: postgres }
  redis:
    image: redis:7-alpine
  qdrant:
    image: qdrant/qdrant:latest

  # Test agents
  echo-agent:
    build: ./agents/echo
    ports: ['8001:8000']
  conversational-agent:
    build: ./agents/conversational
    ports: ['8002:8000']
  proactive-agent:
    build: ./agents/proactive
    ports: ['8003:8000']
  multi-channel-agent:
    build: ./agents/multi_channel
    ports: ['8004:8000']
```

Run E2E tests locally:

```bash
docker compose up -d
sleep 10  # Wait for services
pytest tests/e2e/ -v
docker compose down
```

---

## Test Fixtures (conftest.py)

Common fixtures for the E2E test suite:

```python
import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("INTUNO_BASE_URL", "http://localhost:8000")


@pytest.fixture
async def client():
    async with httpx.AsyncClient(timeout=30) as c:
        yield c


@pytest.fixture
async def auth_token(client):
    """Register a unique test user and return JWT token."""
    email = f"e2e-{uuid.uuid4().hex[:8]}@test.local"
    await client.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "first_name": "E2E",
        "last_name": "Test",
    })
    resp = await client.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": "TestPass123!",
    })
    return resp.json()["access_token"]


@pytest.fixture
async def network(client, auth_token):
    """Create a test network and clean up after."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = await client.post(
        f"{BASE_URL}/networks",
        headers=headers,
        json={"name": f"e2e-test-{uuid.uuid4().hex[:8]}", "topology_type": "mesh"},
    )
    network_data = resp.json()
    yield network_data
    await client.delete(f"{BASE_URL}/networks/{network_data['id']}", headers=headers)


async def add_participant(client, auth_token, network_id, name, callback_url=None, polling=False):
    """Helper to add a participant to a network."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    body = {"name": name, "polling_enabled": polling}
    if callback_url:
        body["callback_url"] = callback_url
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json=body,
    )
    assert resp.status_code == 201
    return resp.json()


async def send_message(client, auth_token, network_id, sender_id, recipient_id, content):
    """Helper to send a message."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/send",
        headers=headers,
        json={
            "sender_participant_id": sender_id,
            "recipient_participant_id": recipient_id,
            "content": content,
        },
    )
    assert resp.status_code == 201
    return resp.json()


async def get_inbox(client, auth_token, network_id, participant_id, limit=50):
    """Helper to poll inbox."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/inbox/{participant_id}",
        headers=headers,
        params={"limit": limit},
    )
    return resp.json()


async def get_context(client, auth_token, network_id, limit=50):
    """Helper to get network context."""
    headers = {"Authorization": f"Bearer {auth_token}"}
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/context",
        headers=headers,
        params={"limit": limit},
    )
    return resp.json()
```

---

## Cleanup Strategy

Every E2E test must clean up after itself to prevent state pollution:

1. Each test creates a **unique network** (random name)
2. Each test registers a **unique user** (random email)
3. After assertions: `DELETE /networks/{id}` removes all participants and messages
4. Use pytest fixtures with `yield` for automatic cleanup on failure

**Never reuse networks or participants across tests.** Each test is fully isolated.
