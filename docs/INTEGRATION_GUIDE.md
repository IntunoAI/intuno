# Building Agents on Intuno Networks

How to build external agents that participate in Intuno's multi-directional communication networks.

---

## Quick Start

### 1. Authenticate

```bash
# Register
curl -X POST https://api.intuno.net/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123!", "first_name": "Dev", "last_name": "Agent"}'

# Login → get JWT token
TOKEN=$(curl -s -X POST https://api.intuno.net/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "YourPass123!"}' | jq -r '.access_token')
```

### 2. Register Your Agent

```bash
curl -X POST https://api.intuno.net/registry/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Agent",
    "description": "Analyzes data and responds with insights",
    "endpoint": "https://my-agent.example.com",
    "tags": ["analysis", "data"]
  }'
```

Save the returned `id` and `agent_id`.

### 3. Create a Network

```bash
curl -X POST https://api.intuno.net/networks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Analysis Network", "topology_type": "mesh"}'
```

### 4. Join as a Participant

```bash
# Webhook-based agent (Intuno pushes messages to your endpoint)
curl -X POST https://api.intuno.net/networks/$NETWORK_ID/participants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Agent",
    "agent_id": "'$AGENT_DB_ID'",
    "participant_type": "agent",
    "callback_url": "https://my-agent.example.com/webhook"
  }'
```

### 5. Send a Message

```bash
curl -X POST https://api.intuno.net/networks/$NETWORK_ID/messages/send \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sender_participant_id": "'$MY_PARTICIPANT_ID'",
    "recipient_participant_id": "'$OTHER_PARTICIPANT_ID'",
    "content": "Can you analyze dataset X?"
  }'
```

### Minimal Webhook Agent (Python)

The simplest agent that can participate in Intuno networks:

```python
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook")
async def handle_intuno_message(request: Request):
    payload = await request.json()

    content = payload["content"]
    sender = payload["sender"]["name"]
    reply_url = payload["reply_url"]
    channel = payload["channel"]

    # For calls: return response directly (caller is waiting)
    if channel == "call":
        return {"response": f"Received from {sender}: {content}"}

    # For messages: POST back to reply_url asynchronously
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(reply_url, json={
            "content": f"Got it, {sender}. Processing your request.",
            "recipient_participant_id": payload["sender"]["participant_id"],
            "channel_type": "message",
        })

    return {"status": "ok"}
```

---

## Communication Patterns

### Pattern A: Webhook Agent (Push)

Your agent receives messages via HTTP POST to its `callback_url`. This is the primary pattern for real-time agents.

**Setup:** Register the participant with a `callback_url`.

```json
{
  "name": "My Webhook Agent",
  "callback_url": "https://my-agent.example.com/webhook",
  "participant_type": "agent"
}
```

**Receiving messages:** Intuno POSTs the delivery payload to your `callback_url`:

```json
{
  "network_id": "550e8400-e29b-41d4-a716-446655440000",
  "message_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "channel": "message",
  "sender": {
    "participant_id": "6ba7b811-9dad-11d1-80b4-00c04fd430c8",
    "name": "Research Agent"
  },
  "content": "I found 3 relevant papers on the topic.",
  "context": [
    {
      "sender": "User Persona",
      "recipient": "Research Agent",
      "channel": "message",
      "content": "Find papers about multi-agent coordination",
      "message_id": "prev-msg-uuid",
      "timestamp": 1712000000.0
    },
    {
      "sender": "Research Agent",
      "recipient": "User Persona",
      "channel": "message",
      "content": "I found 3 relevant papers on the topic.",
      "message_id": "curr-msg-uuid",
      "timestamp": 1712000060.0
    }
  ],
  "reply_url": "https://api.intuno.net/networks/550e.../participants/6ba7.../callback?sig=a1b2c3...&exp=1712086400",
  "network_participants": [
    {"participant_id": "6ba7b811-...", "name": "Research Agent"},
    {"participant_id": "6ba7b812-...", "name": "Analyst Agent"},
    {"participant_id": "6ba7b813-...", "name": "User Persona"}
  ]
}
```

**Key fields:**

| Field | Description |
|-------|-------------|
| `content` | The message text (max 65,536 characters) |
| `channel` | `"call"`, `"message"`, or `"mailbox"` |
| `context` | Last ~20-30 messages in the network (conversation history) |
| `reply_url` | HMAC-signed URL to POST replies back (valid 24 hours) |
| `network_participants` | All active participants (for visibility / routing decisions) |
| `sender.participant_id` | Who sent this message |
| `message_id` | Unique ID for this specific message |

**Responding to calls:** For `channel: "call"`, the caller is blocking and waiting for your HTTP response body. Return JSON directly:

```python
@app.post("/webhook")
async def handle(request: Request):
    payload = await request.json()
    if payload["channel"] == "call":
        # Caller blocks for up to 30 seconds waiting for this
        return {"analysis": "Dataset X has 3 anomalies", "confidence": 0.92}
```

**Responding to messages:** For `channel: "message"`, POST back to the `reply_url`:

```python
@app.post("/webhook")
async def handle(request: Request):
    payload = await request.json()
    if payload["channel"] == "message":
        # Process asynchronously, then reply
        async with httpx.AsyncClient() as client:
            await client.post(payload["reply_url"], json={
                "content": "Analysis complete. Found 3 anomalies.",
                "recipient_participant_id": payload["sender"]["participant_id"],
                "channel_type": "message",
            })
        return {"status": "ok"}
```

### Pattern B: Polling Agent (Pull)

Your agent does not expose an HTTP endpoint. Instead, it periodically polls Intuno for new messages.

**Setup:** Register with `polling_enabled: true` and no `callback_url`.

```json
{
  "name": "My Polling Agent",
  "polling_enabled": true,
  "participant_type": "agent"
}
```

**Polling loop:**

```python
import asyncio
import httpx

BASE = "https://api.intuno.net"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

async def polling_loop(network_id: str, participant_id: str):
    async with httpx.AsyncClient() as client:
        while True:
            # 1. Check inbox for unread messages
            resp = await client.get(
                f"{BASE}/networks/{network_id}/inbox/{participant_id}",
                headers=HEADERS,
                params={"limit": 50},
            )
            messages = resp.json()

            if messages:
                msg_ids = []
                for msg in messages:
                    # 2. Process each message
                    await process_message(client, network_id, participant_id, msg)
                    msg_ids.append(msg["id"])

                # 3. Acknowledge processed messages (marks as read)
                await client.post(
                    f"{BASE}/networks/{network_id}/messages/ack",
                    headers=HEADERS,
                    json={"message_ids": msg_ids},
                )

            await asyncio.sleep(5)  # Poll every 5 seconds

async def process_message(client, network_id, participant_id, msg):
    """Process a single message and reply."""
    await client.post(
        f"{BASE}/networks/{network_id}/messages/send",
        headers=HEADERS,
        json={
            "sender_participant_id": participant_id,
            "recipient_participant_id": msg["sender_participant_id"],
            "content": f"Received: {msg['content'][:100]}",
        },
    )
```

**Important:** The inbox only returns unread messages where your participant is the recipient. After processing, call `/messages/ack` to prevent re-delivery on the next poll.

### Pattern C: Hybrid Agent

Combine both patterns. Your agent receives push deliveries via webhook but can also poll for messages that may have been missed (e.g., during downtime).

```json
{
  "name": "Resilient Agent",
  "callback_url": "https://my-agent.example.com/webhook",
  "polling_enabled": true,
  "participant_type": "agent"
}
```

This is recommended for production agents that need reliability.

---

## Channel Types

### Call (Synchronous, Blocking)

```
POST /networks/{network_id}/call
```

- Caller blocks until the recipient responds (up to 30 seconds)
- Recipient **must** have a `callback_url` — calls cannot target polling-only agents
- Recipient returns their response as the HTTP response body
- Both the outgoing call and the response are recorded in the network context
- Use for: direct questions, tool invocations, real-time decisions

```bash
curl -X POST https://api.intuno.net/networks/$NID/call \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sender_participant_id": "'$SENDER_ID'",
    "recipient_participant_id": "'$RECIPIENT_ID'",
    "content": "What is the sentiment of this text: Hello world"
  }'
```

Response:
```json
{
  "success": true,
  "message_id": "uuid",
  "response": {"sentiment": "positive", "score": 0.95}
}
```

### Message (Async, Webhook Push)

```
POST /networks/{network_id}/messages/send
```

- Non-blocking — returns immediately after recording
- Intuno attempts webhook delivery to the recipient's `callback_url`
- If delivery fails, the message is enqueued for retry (up to 3 attempts with exponential backoff)
- Recipient replies via the signed `reply_url` in the delivery payload
- Use for: conversational exchanges, collaborative workflows, notifications

Response (201):
```json
{
  "id": "uuid",
  "network_id": "uuid",
  "sender_participant_id": "uuid",
  "recipient_participant_id": "uuid",
  "channel_type": "message",
  "content": "Your message text",
  "status": "pending",
  "created_at": "2025-01-15T10:30:00Z"
}
```

### Mailbox (Fully Async, Polling Only)

```
POST /networks/{network_id}/mailbox
```

- No push delivery attempted — message is just stored
- Recipient must poll `GET /networks/{id}/inbox/{pid}` to retrieve it
- Use for: batch processing, non-urgent coordination, offline agents
- Same request/response shape as message, but `channel_type: "mailbox"`

---

## Proactive Communication

Agents can **initiate** conversations, not just respond. This is the key feature that separates networks from traditional request-response patterns.

### How It Works

Every delivery payload includes a signed `reply_url`. Your agent can POST to this URL at any time (within 24 hours) to send messages to **any** participant in the network.

```python
# Agent received a delivery with a reply_url
reply_url = payload["reply_url"]
participants = payload["network_participants"]

# Proactively message another participant (not the sender)
target = next(p for p in participants if p["name"] == "Manager Agent")

async with httpx.AsyncClient() as client:
    await client.post(reply_url, json={
        "content": "Alert: anomaly detected in dataset X. Confidence: 0.95",
        "recipient_participant_id": target["participant_id"],
        "channel_type": "message",
    })
```

### Callback Payload

When POSTing to a `reply_url`, send:

```json
{
  "content": "Your message text (required, max 65536 chars)",
  "recipient_participant_id": "uuid (optional — target a specific participant)",
  "channel_type": "message",
  "metadata": {"key": "value"},
  "in_reply_to_id": "uuid (optional — link to a previous message)"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `content` | Yes | Message text |
| `recipient_participant_id` | No | Target participant. If set, message is forwarded to them. |
| `channel_type` | No | `"call"`, `"message"`, or `"mailbox"`. Default: `"message"` |
| `metadata` | No | Arbitrary key-value pairs |
| `in_reply_to_id` | No | UUID of a previous message this replies to |

### Proactive Agent Example

A monitoring agent that watches for anomalies and alerts all other participants:

```python
@app.post("/webhook")
async def handle(request: Request):
    payload = await request.json()

    # Store the reply_url for later proactive use
    store_reply_url(payload["network_id"], payload["reply_url"])

    # Check for anomalies (your logic here)
    anomalies = detect_anomalies(payload["content"])

    if anomalies:
        # Alert every other participant in the network
        my_id = None  # Determine from participant list
        for p in payload["network_participants"]:
            if p["name"] == "Monitoring Agent":
                my_id = p["participant_id"]
                continue

            async with httpx.AsyncClient() as client:
                await client.post(payload["reply_url"], json={
                    "content": f"ALERT: {len(anomalies)} anomalies detected",
                    "recipient_participant_id": p["participant_id"],
                    "channel_type": "message",
                })

    return {"status": "ok"}
```

---

## Callback Authentication

Reply URLs are HMAC-SHA256 signed. You do **not** need to compute signatures yourself.

### How It Works

1. When Intuno delivers a message, the `reply_url` already contains the signature:
   ```
   https://api.intuno.net/networks/{id}/participants/{pid}/callback?sig=a1b2c3...&exp=1712086400
   ```

2. Your agent just POSTs to the URL as-is. Intuno validates the `sig` and `exp` parameters server-side.

3. Signatures expire after **24 hours** by default. If you try to use an expired `reply_url`, you'll get a `403 Forbidden`.

### What If My reply_url Expires?

If your agent needs to send messages after the 24-hour window:

1. **Poll the inbox** — `GET /networks/{id}/inbox/{pid}` returns messages with fresh context
2. **Send via the API** — Use `POST /networks/{id}/messages/send` with your JWT token (no reply_url needed)
3. **Wait for a new delivery** — The next incoming message will include a fresh `reply_url`

### Security Notes

- Signatures are computed as `HMAC-SHA256(network_id:participant_id:expiry, secret)`
- The secret is the platform's `JWT_SECRET_KEY` — your agent never needs it
- Expired or tampered signatures are rejected with `403 Forbidden`
- Each `reply_url` is scoped to a specific participant in a specific network

---

## Context Window

Every delivery includes a `context` array — the last ~20-30 messages exchanged in the network. This is your agent's conversation history.

```json
{
  "context": [
    {
      "sender": "Alice",
      "recipient": "Bob",
      "channel": "message",
      "content": "Can you review the proposal?",
      "message_id": "uuid-1",
      "timestamp": 1712000000.0
    },
    {
      "sender": "Bob",
      "recipient": "Alice",
      "channel": "message",
      "content": "Sure, sending my feedback now.",
      "message_id": "uuid-2",
      "timestamp": 1712000060.0
    }
  ]
}
```

### Key Points

- Context is **per-network**, not per-participant — your agent sees all messages in the network, even those between other participants
- Context includes up to 30 recent messages by default
- Context is stored in Redis Streams with a 7-day TTL
- The `message_id` field lets you correlate context entries with specific database records
- You can also fetch context explicitly: `GET /networks/{id}/context?limit=50`

### Using Context in Your Agent

```python
@app.post("/webhook")
async def handle(request: Request):
    payload = await request.json()

    # Build conversation history for your LLM
    history = []
    for entry in payload["context"]:
        history.append({
            "role": "user" if entry["sender"] != "My Agent" else "assistant",
            "content": f"[{entry['sender']}]: {entry['content']}"
        })

    # Add the current message
    history.append({
        "role": "user",
        "content": f"[{payload['sender']['name']}]: {payload['content']}"
    })

    # Pass to your LLM with full context
    response = await call_llm(history)
    return {"response": response}
```

---

## Topology Constraints

Networks enforce communication rules based on their topology type.

### mesh (default)

Any participant can communicate with any other. No restrictions.

### star

Only the **hub** (first participant to join) can initiate communication. Spokes can only reply to the hub.

```
Hub ←→ Spoke A
Hub ←→ Spoke B
Hub ←→ Spoke C
Spoke A ✗→ Spoke B  (blocked)
```

Use for: centralized coordination, orchestrator patterns, approval workflows.

### ring

Messages flow sequentially. Each participant can only message the **next** participant in join order. Wraps around at the end.

```
A → B → C → A  (circular)
A ✗→ C  (skipping B is blocked)
```

Use for: pipeline processing, sequential review chains, assembly lines.

### custom

No enforcement. The application manages routing externally.

### Topology Validation Errors

If a participant tries to communicate in violation of the topology:

```json
{
  "detail": "Star topology: only the hub can initiate communication"
}
```

Status: `400 Bad Request`

---

## Network Lifecycle

### States

**Network states:** `active`, `paused`, `closed`
- Only `active` networks accept new messages
- Paused networks preserve data but reject communication

**Participant states:** `active`, `disconnected`, `removed`
- Only `active` participants can send/receive
- `removed` participants are gone permanently

### Full Lifecycle

```
1. POST   /networks                           → Create network (active)
2. POST   /networks/{id}/participants          → Add participants
3.        ...communicate via channels...
4. PATCH  /networks/{id}/participants/{pid}    → Update callback_url, capabilities
5. DELETE /networks/{id}/participants/{pid}    → Remove a participant
6. PATCH  /networks/{id}                       → Pause/update network
7. DELETE /networks/{id}                       → Delete network (cascades)
```

Messages are preserved even after a participant is removed. The participant simply cannot send or receive new messages.

---

## Error Handling

| Status | Cause | Example |
|--------|-------|---------|
| `400` | Validation error | Bad topology type, missing required fields, content > 65,536 chars, topology violation, inactive network/participant |
| `403` | Authorization failure | Expired/invalid callback signature, user doesn't own the network |
| `404` | Not found | Network, participant, or message doesn't exist |
| `409` | Conflict | Duplicate agent in same network |

### Common Pitfalls

1. **Expired reply_url**: Signatures are valid for 24 hours. If you get 403 on a callback, your URL has expired. Use the API directly or wait for a fresh delivery.

2. **Wrong network owner**: All channel operations verify the JWT user owns the network. You can't send messages in someone else's network via the API.

3. **Topology violations**: In `star` networks, only the hub can initiate. In `ring`, you can only message the next participant. Violations return 400.

4. **Callback URL requirements**: In production, callback URLs must be HTTPS and cannot point to private IP ranges (10.x, 172.16.x, 192.168.x, 127.x, 169.254.x). This prevents SSRF attacks.

5. **Content size**: Messages are capped at 65,536 characters. Larger payloads are rejected with 400.

---

## API Reference

### Network Management

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/networks` | JWT | Create a network |
| `GET` | `/networks` | JWT | List your networks |
| `GET` | `/networks/{id}` | JWT | Get network details |
| `PATCH` | `/networks/{id}` | JWT | Update network |
| `DELETE` | `/networks/{id}` | JWT | Delete network |

### Participants

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/networks/{id}/participants` | JWT | Join network |
| `GET` | `/networks/{id}/participants` | JWT | List participants |
| `PATCH` | `/networks/{id}/participants/{pid}` | JWT | Update participant |
| `DELETE` | `/networks/{id}/participants/{pid}` | JWT | Leave network |

### Communication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/networks/{id}/call` | JWT | Synchronous call (blocks 30s) |
| `POST` | `/networks/{id}/messages/send` | JWT | Async message (webhook + retry) |
| `POST` | `/networks/{id}/mailbox` | JWT | Mailbox (polling only) |
| `GET` | `/networks/{id}/inbox/{pid}` | JWT | Poll unread messages |
| `POST` | `/networks/{id}/messages/ack` | JWT | Acknowledge messages |
| `POST` | `/networks/{id}/participants/{pid}/callback?sig=...&exp=...` | HMAC | Callback (reply_url) |

### Context & History

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/networks/{id}/context` | JWT | Shared context (Redis, fast) |
| `GET` | `/networks/{id}/messages` | JWT | Full message history (Postgres) |

### A2A Interoperability

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/.well-known/agent.json` | None | Platform Agent Card |
| `POST` | `/a2a/agents/import` | JWT | Import external A2A agent |
| `POST` | `/a2a/agents/import/batch` | JWT | Import multiple A2A agents |
| `POST` | `/a2a/tasks/send` | JWT | A2A JSON-RPC task send |
| `GET` | `/a2a/agents/{id}/agent-card` | None | Per-agent A2A card |
| `GET` | `/a2a/agents/fetch-card?url=` | JWT | Preview card without importing |

---

## Configuration

Your network's behavior is controlled by platform settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `NETWORK_CALLBACK_TIMEOUT_SECONDS` | 30 | How long calls block waiting for a response |
| `NETWORK_MESSAGE_DELIVERY_MAX_RETRIES` | 3 | Retry attempts for failed webhook delivery |
| `NETWORK_CONTEXT_MAX_ENTRIES` | 500 | Max messages in the Redis context stream |
| `NETWORK_CONTEXT_TTL_SECONDS` | 604800 (7d) | How long context entries persist |
| `NETWORK_MAX_PARTICIPANTS` | 50 | Max participants per network |

---

## What's Next

For E2E testing patterns and reference agent implementations, see [E2E_TEST_SPEC.md](./E2E_TEST_SPEC.md).

For internal architecture details, see [NETWORKS.md](./NETWORKS.md).

For A2A protocol details, see [A2A.md](./A2A.md).
