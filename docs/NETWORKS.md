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

When Intuno delivers any communication to an external agent, the payload includes a `reply_url`:

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
    {"sender": "User", "recipient": "Writer Agent", "channel": "message", "content": "...", "timestamp": 1711900000}
  ],
  "reply_url": "https://api.intuno.net/networks/{id}/participants/{pid}/callback",
  "network_participants": [
    {"participant_id": "uuid", "name": "Writer Agent"},
    {"participant_id": "uuid", "name": "Reviewer Agent"}
  ]
}
```

The external agent can POST back to the `reply_url` to proactively send messages into the network. No authentication is required on the callback — the URL itself acts as a capability token.

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
     → POST to Agent B's callback_url (with context + reply_url)

4. Agent B responds proactively
   POST /networks/{id}/participants/{B}/callback
     → Record in DB + Redis context
     → Forward to Agent A if targeted (with updated context)
```

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
│   └── schemas.py          # Pydantic request/response schemas
├── repositories/
│   └── networks.py         # CRUD + context retrieval
├── services/
│   ├── networks.py         # Network management + message recording
│   └── channels.py         # Calls, messages, mailboxes, callbacks
├── routes/
│   ├── networks.py         # Network + participant + context endpoints
│   ├── channels.py         # Call/message/mailbox/inbox endpoints
│   └── callbacks.py        # External agent callback receiver
├── utils/
│   ├── context_manager.py  # Redis Streams context accumulator
│   ├── delivery_worker.py  # Background message delivery (Redis Streams consumer)
│   ├── topology.py         # Topology validation and routing
│   ├── convergence.py      # Convergence detectors for loops
│   └── aggregator.py       # Fan-in aggregation strategies
└── a2a/
    ├── agent_card.py       # A2A Agent Card generation
    ├── protocol.py         # A2A ↔ Intuno format translation
    ├── discovery.py        # Fetch + import external A2A agents
    └── routes.py           # A2A-compatible API endpoints
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
