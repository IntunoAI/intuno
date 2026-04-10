# Communication Networks

Multi-directional agent communication with shared context.

---

## Overview

A **Communication Network** groups agents (participants) that can exchange messages bidirectionally. Unlike the broker (one-way request-response), networks enable agents to proactively initiate communication with each other.

The system solves two fundamental limitations:

1. **Directionality** — the broker only supports caller → callee. Networks allow any participant to message any other.
2. **Invocability asymmetry** — invoking agents weren't registered as invocable endpoints. In a network, every participant must register how they can be reached.

---

## Core Concepts

### Participants

Any agent can join a network by registering either:

- A **callback URL** — Intuno POSTs messages to this endpoint
- **Polling** — the participant checks their inbox via the API

This means any agent registered in Intuno (simple registration or A2A import) can participate.

### Three Communication Channels

| Channel | Timing | Delivery | Use Case |
|---------|--------|----------|----------|
| **Call** | Synchronous, blocking | HTTP request-response | Direct questions, immediate responses |
| **Message** | Near-real-time, non-blocking | Webhook push | Conversational, like chat |
| **Mailbox** | Fully async | Polling only | Batch processing, non-urgent coordination |

### Shared Context

Every message exchanged within a network is recorded and accumulated. When Intuno delivers a message to a participant, the payload includes recent conversation history so the agent has context — even if it wasn't part of earlier exchanges.

### The `reply_url` Pattern

When Intuno delivers any communication to an external agent, the payload includes a signed `reply_url`:

```json
{
  "network_id": "uuid",
  "message_id": "uuid",
  "channel": "call",
  "sender": {
    "participant_id": "uuid",
    "name": "Writer Agent"
  },
  "content": "Please review this draft...",
  "context": [
    {"sender": "User", "recipient": "Writer Agent", "channel": "message", "content": "...", "message_id": "uuid", "timestamp": 1711900000}
  ],
  "reply_url": "https://api.intuno.net/networks/{id}/participants/{pid}/callback?sig=abc123...&exp=1712000000",
  "network_participants": [
    {"participant_id": "uuid", "name": "Writer Agent"},
    {"participant_id": "uuid", "name": "Reviewer Agent"}
  ]
}
```

The external agent can POST back to the `reply_url` to proactively send messages into the network. The callback URL is HMAC-SHA256 signed — the `sig` and `exp` query parameters are validated server-side. Signatures expire after 24 hours (configurable). The agent does not need to compute signatures; just POST to the URL as provided.

### Security

- **Callback authentication**: Reply URLs are HMAC-SHA256 signed (`src/network/utils/callback_auth.py`). Invalid or expired signatures are rejected with 403.
- **Ownership checks**: All channel operations verify the calling user owns the network. Authenticated users cannot send messages in networks they don't own.
- **SSRF protection**: Callback URLs are validated against private IP ranges (10.x, 172.16.x, 192.168.x, 127.x, 169.254.x, IPv6 loopback/ULA). HTTPS is required in production.
- **Content limits**: All message content is capped at 65,536 characters.
- **Topology enforcement**: Communication constraints (star hub-only, ring sequential) are enforced at the service layer — invalid sends return 400.

---

## Topology Types

Networks support four topology types that constrain communication patterns:

| Topology | Rule |
|----------|------|
| **mesh** (default) | Any participant can communicate with any other |
| **star** | Only the hub (first participant) can initiate |
| **ring** | Messages flow sequentially to the next participant |
| **custom** | No enforcement; topology managed externally |

---

## API Endpoints

### Networks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/networks` | Create a network |
| GET | `/networks` | List networks (owner-scoped) |
| GET | `/networks/{id}` | Get network details |
| PATCH | `/networks/{id}` | Update network |
| DELETE | `/networks/{id}` | Delete network |

### Participants

| Method | Path | Description |
|--------|------|-------------|
| POST | `/networks/{id}/participants` | Join network |
| GET | `/networks/{id}/participants` | List participants |
| PATCH | `/networks/{id}/participants/{pid}` | Update participant |
| DELETE | `/networks/{id}/participants/{pid}` | Leave network |

### Channels

| Method | Path | Description |
|--------|------|-------------|
| POST | `/networks/{id}/call` | Synchronous call |
| POST | `/networks/{id}/messages/send` | Send async message |
| POST | `/networks/{id}/mailbox` | Send to mailbox |
| GET | `/networks/{id}/inbox/{pid}` | Poll inbox |
| POST | `/networks/{id}/messages/ack` | Acknowledge messages |

### Callbacks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/networks/{id}/participants/{pid}/callback` | Receive message from external agent |

### Context

| Method | Path | Description |
|--------|------|-------------|
| GET | `/networks/{id}/context` | Get shared context (Redis-cached) |
| GET | `/networks/{id}/messages` | List all messages (Postgres) |

---

## Data Flow

```
1. Create network
   POST /networks  →  CommunicationNetwork (mesh, active)

2. Add participants
   POST /networks/{id}/participants  →  callback_url or polling_enabled

3. Agent A sends message to Agent B
   POST /networks/{id}/messages/send
     → Record in DB + Redis context
     → POST to Agent B's callback_url (with context + signed reply_url)
     → If delivery fails → enqueue for retry via DeliveryWorker (Redis Streams)

4. Agent B responds proactively
   POST /networks/{id}/participants/{B}/callback?sig=...&exp=...
     → Verify HMAC signature (reject if invalid/expired)
     → Record in DB + Redis context
     → Forward to Agent A if targeted (with updated context)
```

### Delivery Worker

Failed webhook deliveries are automatically retried by a background worker (`src/network/utils/delivery_worker.py`) that consumes from a Redis Stream. Retries use exponential backoff (2, 4, 8 seconds) with a configurable maximum (default: 3 retries). The worker starts automatically with the application.

---

## Workflow Integration: Loops and Aggregation

### Loop Steps (Feedback Cycles)

The workflow DSL supports `loop` steps for iterative agent interactions:

```yaml
- id: review_loop
  type: loop
  loop:
    max_iterations: 5
    convergence:
      type: similarity
      threshold: 0.95
    body:
      - id: write
        agent: "writer-agent"
      - id: review
        agent: "reviewer-agent"
```

**Convergence detectors:**

| Type | Behavior |
|------|----------|
| `similarity` | Compares consecutive outputs (Jaccard token overlap). Stops when similarity ≥ threshold. |
| `approval` | Checks for approval keywords ("approved", "lgtm") or `{"approved": true}` in output. |
| `max_iterations` | Hard cap. Always enforced as a safety net. |

### Aggregate Steps (Fan-In)

Combine outputs from multiple parallel agents:

```yaml
- id: collect
  type: aggregate
  aggregate:
    sources: [agent_a, agent_b, agent_c]
    strategy: llm_summarize
    timeout_seconds: 30
```

**Strategies:**

| Strategy | Behavior |
|----------|----------|
| `merge` | Concatenate all outputs into a single dict, keyed by source step ID |
| `vote` | Pick the majority answer (for classification tasks) |
| `llm_summarize` | Use LLM to synthesize all inputs into a coherent output |

---

## File Layout

```
src/network/
├── __init__.py
├── models/
│   ├── entities.py         # CommunicationNetwork, NetworkParticipant, NetworkMessage
│   └── schemas.py          # Pydantic request/response schemas (Literal types, content limits)
├── repositories/
│   └── networks.py         # CRUD + context retrieval + get_inbox (unread/recipient-only)
├── services/
│   ├── networks.py         # Network management + SSRF-safe URL validation on join
│   └── channels.py         # Calls, messages, mailboxes, callbacks + ownership checks + topology
├── routes/
│   ├── networks.py         # Network + participant + context endpoints
│   ├── channels.py         # Call/message/mailbox/inbox endpoints
│   └── callbacks.py        # HMAC-authenticated callback receiver
├── utils/
│   ├── callback_auth.py    # HMAC-SHA256 signed reply_url generation and verification
│   ├── url_validator.py    # SSRF-safe URL validation (rejects private IPs)
│   ├── context_manager.py  # Redis Streams context accumulator (includes message_id)
│   ├── delivery_worker.py  # Background retry worker (Redis Streams consumer, exponential backoff)
│   ├── topology.py         # Topology validation (mesh, star, ring, custom)
│   ├── convergence.py      # Convergence detectors for loops
│   └── aggregator.py       # Fan-in aggregation strategies
└── a2a/
    ├── agent_card.py       # A2A Agent Card generation
    ├── protocol.py         # A2A ↔ Intuno format translation
    ├── discovery.py        # Fetch + import external A2A agents (with URL validation)
    └── routes.py           # A2A-compatible API endpoints (session-safe via Depends)
```

---

## Configuration

Settings in `src/core/settings.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `NETWORK_CONTEXT_TTL_SECONDS` | 604800 (7 days) | Redis context stream TTL |
| `NETWORK_CONTEXT_MAX_ENTRIES` | 500 | Max messages in Redis context stream |
| `NETWORK_MAX_PARTICIPANTS` | 50 | Max participants per network |
| `NETWORK_CALLBACK_TIMEOUT_SECONDS` | 30 | HTTP timeout for callback delivery |
| `NETWORK_MESSAGE_DELIVERY_MAX_RETRIES` | 3 | Retry count for failed deliveries |
