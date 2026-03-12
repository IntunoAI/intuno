# Test Coverage Tracker

## Test Files

| File | Purpose | Tests | Status |
|------|---------|-------|--------|
| `test_workflow.py` | Backend API endpoint coverage (raw HTTP) | ~30 | Passing |
| `test_sdk_integration.py` | Intuno SDK client validation (sync + async) | 9 | Partial (chat-agent compat) |
| `test_user_session.py` | Multi-turn sessions, user isolation, history (OpenAI-powered) | 10 | Passing |
| `run_all.sh` | Runner script for all three suites | — | — |

## Running Tests

```bash
cd wisdom

# All suites
bash tests/run_all.sh

# Individual
python -m tests.test_workflow --base-url http://localhost:8000
python -m tests.test_sdk_integration --base-url http://localhost:8000
python -m tests.test_user_session --base-url http://localhost:8000
```

Prerequisites: Wisdom backend on :8000, wisdom-agents on :8001, PostgreSQL, Qdrant, `OPENAI_API_KEY` in `.env` (for user session tests).

---

## Endpoint Coverage

### Auth (`/auth`) — 6 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `POST /auth/register` | ✅ | ✅ | ✅ | |
| `POST /auth/login` | ✅ | — | ✅ | |
| `GET /auth/me` | ✅ | — | — | |
| `POST /auth/api-keys` | ✅ | ✅ | ✅ | |
| `GET /auth/api-keys` | ✅ | — | — | |
| `DELETE /auth/api-keys/{key_id}` | — | — | — | **Missing** |

### Brands (`/brands`) — 6 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `POST /brands` | — | — | — | **Missing** |
| `GET /brands/me` | — | — | — | **Missing** |
| `GET /brands/{id_or_slug}` | — | — | — | **Missing** |
| `PUT /brands/{brand_id}` | — | — | — | **Missing** |
| `POST /brands/{brand_id}/resend-verification` | — | — | — | **Missing** |
| `POST /brands/{brand_id}/verify` | — | — | — | **Missing** |

### Broker (`/broker`) — 1 route

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `POST /broker/invoke` | ✅ | ✅ | ✅ | Personal key + integration key + multi-turn |

### Conversations (`/conversations`) — 6 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `GET /conversations` | ✅ | — | ✅ | Filtered by `external_user_id` |
| `GET /conversations/{id}` | ✅ | — | ✅ | |
| `PATCH /conversations/{id}` | — | — | — | **Missing** |
| `DELETE /conversations/{id}` | — | — | — | **Missing** (skipped: destructive) |
| `GET /conversations/{id}/logs` | ✅ | — | ✅ | |
| `GET /conversations/{id}/messages` | ✅ | — | ✅ | |

### Health (`/health`) — 1 route

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `GET /health` | ✅ | — | — | |

### Integrations (`/integrations`) — 7 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `POST /integrations` | ✅ | — | ✅ | |
| `GET /integrations` | ✅ | — | — | |
| `GET /integrations/{id}` | ✅ | — | — | |
| `DELETE /integrations/{id}` | — | — | — | **Missing** (skipped: destructive) |
| `GET /integrations/{id}/api-keys` | ✅ | — | — | |
| `POST /integrations/{id}/api-keys` | ✅ | — | ✅ | |
| `DELETE /integrations/{id}/api-keys/{key_id}` | — | — | — | **Missing** (skipped: destructive) |

### Invocation Logs (`/broker/logs`) — 2 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `GET /broker/logs` | ✅ | — | — | |
| `GET /broker/logs/agent/{agent_id}` | ✅ | — | — | |

### Messages (`/conversations/{id}/messages`) — 2 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `GET .../messages/{message_id}` | — | — | — | **Missing** |
| `DELETE .../messages/{message_id}` | — | — | — | **Missing** (skipped: destructive) |

### Registry (`/registry`) — 11 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `POST /registry/agents` | — | — | — | Skipped: agents pre-registered |
| `GET /registry/agents` | ✅ | — | ✅ | |
| `GET /registry/agents/new` | ✅ | — | — | |
| `GET /registry/agents/trending` | ✅ | — | — | |
| `GET /registry/agents/{agent_id}` | ✅ | — | — | |
| `PUT /registry/agents/{agent_uuid}` | — | — | — | **Missing** |
| `DELETE /registry/agents/{agent_uuid}` | — | — | — | Skipped: destructive |
| `POST /registry/agents/{id}/rate` | ✅ | — | — | |
| `GET /registry/agents/{id}/ratings` | ✅ | — | — | |
| `GET /registry/discover` | ✅ | ✅ | — | Semantic search |
| `GET /registry/my-agents` | ✅ | — | — | |

### Tasks (`/tasks`) — 2 routes

| Endpoint | Workflow | SDK | Session | Notes |
|----------|:--------:|:---:|:-------:|-------|
| `POST /tasks` | ✅ | ✅ | ✅ | Sync + async modes |
| `GET /tasks/{task_id}` | ✅ | ✅ | ✅ | Polling tested |

---

## Coverage Summary

| Category | Total Routes | Covered | Missing |
|----------|:-----------:|:-------:|:-------:|
| Auth | 6 | 5 | 1 |
| Brands | 6 | 0 | **6** |
| Broker | 1 | 1 | 0 |
| Conversations | 6 | 4 | 2 |
| Health | 1 | 1 | 0 |
| Integrations | 7 | 5 | 2 |
| Invocation Logs | 2 | 2 | 0 |
| Messages | 2 | 0 | **2** |
| Registry | 11 | 8 | 3 |
| Tasks | 2 | 2 | 0 |
| **Total** | **44** | **28** | **16** |

---

## Missing Tests — Prioritized

### P0 — Functional gaps (affects core features)

- [ ] `GET /conversations/{id}/messages/{message_id}` — single message retrieval; now that broker persists messages, this should work
- [ ] `PATCH /conversations/{id}` — update conversation title/metadata; needed for frontend rename flow
- [ ] `PUT /registry/agents/{uuid}` — agent manifest update; critical for agent owners

### P1 — Brand module (entirely untested)

- [ ] `POST /brands` — create brand
- [ ] `GET /brands/me` — list user's brands
- [ ] `GET /brands/{id_or_slug}` — get brand detail
- [ ] `PUT /brands/{brand_id}` — update brand
- [ ] `POST /brands/{brand_id}/resend-verification` — resend email
- [ ] `POST /brands/{brand_id}/verify` — verify brand

### P2 — Destructive actions (skipped intentionally)

- [ ] `DELETE /auth/api-keys/{key_id}` — revoke personal API key
- [ ] `DELETE /conversations/{id}` — delete conversation
- [ ] `DELETE /conversations/{id}/messages/{message_id}` — delete message
- [ ] `DELETE /integrations/{id}` — delete integration
- [ ] `DELETE /integrations/{id}/api-keys/{key_id}` — revoke integration key
- [ ] `DELETE /registry/agents/{uuid}` — deregister agent
- [ ] `POST /registry/agents` — register agent (creates state; skipped since agents are pre-registered)

### P3 — Advanced scenarios (not yet covered)

- [ ] **Sync SDK invoke** — `IntunoClient.invoke()` with a chat-compatible agent (currently gets 422 if calculator is picked first)
- [ ] **Personal API key invoke vs integration key invoke** — different conversation scoping (`integration_id=None`)
- [ ] **Multi-agent conversation** — talk to different agents in the same `conversation_id`
- [ ] **Broker retry/timeout** — agent returning 5xx or timing out; verify retry logic
- [ ] **Quota enforcement** — monthly/daily invocation limits; verify 429 response
- [ ] **Allowlist enforcement** — agent not in integration's `allowed_agent_ids`; verify 403
- [ ] **Error paths** — invalid `agent_id`, invalid `capability_id`, expired API key, malformed input
- [ ] **Concurrent invocations** — parallel broker calls to test DB transaction safety
- [ ] **Frontend/WebSocket chat** — if applicable, browser-based chat flow

---

## Known Issues

1. **SDK integration 422s**: The wisdom-agents server validates all requests through `AgentChatRequest` which only accepts `message`/`query`/`text`/`messages` fields. Non-chat agents (e.g., calculator with `{"a": number, "b": number}`) return 422. The SDK test now prefers chat-compatible agents, but the calculator path remains untestable without agent-side changes.

2. **Agent auth gap**: `auth_type` in manifests is decorative. No per-agent credential mechanism exists. The broker uses a single shared `AGENTS_API_KEY` for all agents. See `.cursor/rules/broker-agent-auth-gap.mdc` for details.

3. **Conversation title**: The broker creates conversations with `title=None`. No auto-titling or first-message summary is implemented.
