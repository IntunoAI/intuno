# Federation of Agents Design Patterns - Implementation Plan

## Executive Summary

This document maps the 5 design patterns from "Federation of Agents" to the Wisdom codebase, identifying what's already implemented, what needs to be added, and what can be deferred. The plan is organized by priority: **MVP (Critical)**, **High Priority**, **Medium Priority**, and **Nice to Have**.

---

## Current State Assessment

### ✅ Already Implemented
- **Basic embeddings**: Agent and capability embeddings using OpenAI
- **Vector search**: Semantic discovery via pgvector (`GET /registry/discover`)
- **Broker service**: Synchronous agent invocation (`POST /broker/invoke`)
- **Invocation logging**: Basic logging of calls (success, latency, errors)
- **Trust field**: Static `trust_verification` field in agent model
- **Capability-level embeddings**: Each capability has its own embedding vector

### ❌ Missing / Incomplete
- VCV versioning and refresh mechanism
- Ranking with metadata (cost, latency, trust scores)
- Metrics computation and trust score calculation
- Orchestration/DAG support
- Async pub/sub messaging
- Enhanced embedding generation (more metadata)

---

## Pattern 1: Capability Embeddings (Versioned Capability Vectors, VCVs)

### Current Implementation Status: **~60% Complete**

#### ✅ What's Working
- Agent embeddings generated on registration/update
- Capability embeddings generated per capability
- Vector storage in PostgreSQL with pgvector
- Semantic search using cosine similarity

#### ❌ What's Missing
1. **VCV versioning**: No `vcv_version` field to track embedding model versions
2. **Manifest-level capability_vector**: Embeddings stored in DB but not exposed in manifest
3. **Refresh endpoint**: No way to re-embed when model upgrades
4. **Enhanced embedding content**: Currently only uses name, description, tags, and basic schema info

### Implementation Plan

#### Priority: **HIGH (MVP+ Week 2)**

#### Tasks

**1. Add VCV Version Tracking** (MVP)
- [ ] Add `vcv_version` field to `Capability` model (default: "0.1")
- [ ] Add `vcv_version` to `Agent` model (for agent-level embeddings)
- [ ] Store embedding model name/version in settings
- [ ] Migration: Add columns to existing tables

**2. Enhanced Embedding Generation** (Nice to Have - Defer)
- [ ] Include metadata in embedding text: cost estimates, latency hints, tags
- [ ] Consider including input/output schema summaries (more detailed)
- **Note**: User mentioned this is "nice to have" - defer to later

**3. Refresh VCV Endpoint** (High Priority)
- [ ] `POST /registry/agents/{agent_uuid}/refresh-vcv` endpoint
- [ ] Re-generate embeddings for agent + all capabilities
- [ ] Update `vcv_version` to current model version
- [ ] Useful when embedding model upgrades

**4. Expose VCV in API Responses** (Medium Priority)
- [ ] Add `vcv_version` to `AgentResponse` and `CapabilitySchema`
- [ ] Optionally expose `capability_vector` in detailed responses (if needed)

### Metrics to Track
- Embedding generation time per agent
- Cost of embedding API calls
- Number of refresh operations

### Risks
- **Embedding model drift**: Mitigated by refresh endpoint
- **Cost**: Batch embedding generation, cache where possible
- **Migration complexity**: Need to backfill vcv_version for existing records

---

## Pattern 2: Semantic Routing & Ranking (Query → Candidate → Score)

### Current Implementation Status: **~40% Complete**

#### ✅ What's Working
- Basic semantic search: `GET /registry/discover?query=...`
- Vector similarity search using pgvector
- Returns agents ordered by similarity

#### ❌ What's Missing
1. **Ranking function**: No metadata-based scoring (cost, latency, trust)
2. **POST endpoint**: Only GET with query params (should support filters in body)
3. **Metadata filters**: No way to filter by cost, latency, trust thresholds
4. **Scoring transparency**: No `score` field in response
5. **Metadata collection**: No cost/latency metadata stored per capability

### Implementation Plan

#### Priority: **HIGH (MVP - Week 3)**

#### Tasks

**1. Add Metadata to Capabilities** (MVP)
- [ ] Add `metadata` JSONB field to `Capability` model
  - `cost_usd`: Estimated cost per invocation
  - `latency_ms`: Expected latency
  - `visibility`: "public" | "private"
- [ ] Update manifest schema to accept capability metadata
- [ ] Migration: Add metadata column

**2. Implement Ranking Function** (MVP)
- [ ] Create `RankingService` with configurable weights:
  ```python
  score = α*similarity + β*(1 - normalized_latency) + γ*(1 - normalized_cost) + δ*trust_score
  ```
- [ ] Default weights: similarity=0.7, latency=0.1, cost=0.1, trust=0.1
- [ ] Normalize latency and cost to 0-1 range
- [ ] Use trust_score from Pattern 4 (or default to 0.5 if not available)

**3. Enhanced Discover Endpoint** (MVP)
- [ ] Convert `GET /registry/discover` to `POST /registry/discover`
- [ ] Request body:
  ```json
  {
    "query": "summarize spanish PDF",
    "filters": {
      "max_cost_usd": 0.01,
      "max_latency_ms": 500,
      "min_trust_score": 0.7
    },
    "max_results": 5
  }
  ```
- [ ] Response includes `score`, `estimated_latency`, `estimated_cost` per result
- [ ] Keep GET endpoint for backward compatibility (deprecate later)

**4. Search Endpoint Enhancement** (Medium Priority)
- [ ] Add ranking to `GET /registry/agents?search=...`
- [ ] Support filters in query params

### Metrics to Track
- Click-through/invoke rate for top-1 candidate
- Average similarity score of matched agents
- % of successful match→invoke flows
- Time to retrieve + rank (latency)

### Risks
- **Overfitting ranking weights**: Provide adaptive defaults, allow A/B testing
- **Missing metadata**: Default values for agents without metadata
- **Performance**: Ranking adds computation - optimize with indexes

---

## Pattern 3: Task Decomposition & Orchestration Hints (Lightweight DAGs)

### Current Implementation Status: **0% Complete**

#### ❌ What's Missing
- No DAG support
- No orchestration API
- No task decomposition
- No workflow execution engine

### Implementation Plan

#### Priority: **MEDIUM (Week 6+)**

#### Staged Approach

**Stage A: Manual DAG Orchestration (MVP - Week 6)**
- [ ] Create `Orchestration` model:
  - `orchestrator_id` (agent UUID)
  - `task_id` (unique task identifier)
  - `dag` (JSONB: `{nodes: [...], edges: [...]}`)
  - `status` (pending, running, completed, failed)
  - `results` (JSONB: aggregated results)
- [ ] `POST /broker/orchestrations` endpoint:
  ```json
  {
    "orchestrator_id": "agent:...",
    "task_id": "task-123",
    "dag": {
      "nodes": [
        {"id": "node1", "agent_id": "...", "capability_id": "..."},
        {"id": "node2", "agent_id": "...", "capability_id": "..."}
      ],
      "edges": [
        {"from": "node1", "to": "node2"}
      ]
    }
  }
  ```
- [ ] Broker executes DAG by invoking agents in topological order
- [ ] `GET /broker/orchestrations/{orchestration_id}` to poll status
- [ ] Support sequential and parallel execution (based on DAG edges)

**Stage B: Decomposition Helper (Later - Week 8+)**
- [ ] `POST /registry/decompose` endpoint (advisory tool)
- [ ] Uses LLM to suggest subtasks and candidate capabilities
- [ ] Returns suggested DAG + candidate agents
- [ ] Human/orchestrator can accept/modify before execution

**Stage C: Advanced Orchestration (Future)**
- [ ] Automatic retry logic
- [ ] Cost optimization (parallel vs sequential)
- [ ] Circuit breakers and timeouts
- [ ] Loop detection

### Metrics to Track
- % of decomposed tasks that succeed first try
- Average task completion time vs single-call baseline
- Number of agents chained per orchestration
- Failure rate by orchestration depth

### Risks
- **Complexity explosion**: Start simple, add features incrementally
- **Cascading failures**: Enforce timeouts, circuit breakers, idempotence
- **Cost**: Long-running orchestrations can be expensive

---

## Pattern 4: Reputation & Trust Signals (Reputation Graph)

### Current Implementation Status: **~30% Complete**

#### ✅ What's Working
- `InvocationLog` tracks: success, latency, errors
- Static `trust_verification` field (self-signed, verified, etc.)

#### ❌ What's Missing
1. **Metrics computation**: No rolling success_rate, avg_latency, error_rate
2. **Trust score calculation**: No computed trust_score field
3. **Metrics API**: No endpoint to get agent metrics
4. **Feedback mechanism**: No way to submit human feedback
5. **Verification workflow**: No admin endpoint to verify agents

### Implementation Plan

#### Priority: **HIGH-MEDIUM (Week 4-5)**

#### Tasks

**1. Metrics Computation** (High Priority)
- [ ] Create `AgentMetrics` model or computed view:
  ```sql
  - success_rate_7d (rolling 7-day window)
  - avg_latency_7d
  - error_rate_7d
  - total_invocations_7d
  - total_cost_7d (if tracking cost)
  ```
- [ ] Create background job or materialized view to compute metrics
- [ ] Update metrics on each invocation (or batch update)

**2. Trust Score Calculation** (High Priority)
- [ ] Compute `trust_score` (0.0 - 1.0) based on:
  - `success_rate_7d` (weight: 0.4)
  - `avg_latency` normalized (weight: 0.2)
  - `trust_verification` badge (weight: 0.3)
    - "verified" = 1.0
    - "self-signed" = 0.5
  - Recent invocation volume (weight: 0.1)
- [ ] Store `trust_score` in `Agent` model (computed field or cached)
- [ ] Update trust_score periodically (e.g., every hour)

**3. Metrics API** (High Priority)
- [ ] `GET /registry/agents/{agent_id}/metrics`
  ```json
  {
    "success_rate_7d": 0.95,
    "avg_latency_ms": 250,
    "error_rate_7d": 0.05,
    "total_invocations_7d": 100,
    "trust_score": 0.87
  }
  ```

**4. Feedback Endpoint** (Medium Priority)
- [ ] `POST /registry/agents/{agent_id}/feedback`
  ```json
  {
    "rating": 1-5,
    "comment": "optional",
    "user_id": "..."
  }
  ```
- [ ] Store feedback in `AgentFeedback` model
- [ ] Incorporate into trust_score calculation (optional)

**5. Verification Endpoint** (Low Priority - Admin Only)
- [ ] `PATCH /registry/agents/{agent_id}/verify` (admin only)
- [ ] Update `trust_verification` to "verified"
- [ ] Requires admin role/permission

### Metrics to Track
- % of calls routed to agents with trust_score > threshold
- Reduction in failed invocations after filtering by trust_score
- Trust score distribution across network

### Risks
- **Sybil/manipulation**: Require auth & rate limiting; use org verification for higher trust
- **Cold start problem**: New agents have no metrics - use default trust_score
- **Computation cost**: Materialized views or background jobs needed

---

## Pattern 5: Lightweight Pub/Sub Fabric & Broker Patterns

### Current Implementation Status: **~50% Complete**

#### ✅ What's Working
- Synchronous broker: `POST /broker/invoke` (proxied calls)
- Request/response logging

#### ❌ What's Missing
1. **Async messaging**: No queue-based async invocations
2. **Webhooks**: No webhook subscriptions for events
3. **Pub/Sub**: No publish/subscribe messaging fabric
4. **Event subscriptions**: No way to subscribe to agent events

### Implementation Plan

#### Priority: **MEDIUM (Week 7-8)**

#### Tasks

**1. Async Invocation Support** (Medium Priority)
- [ ] Add `async: bool` flag to `InvokeRequest`
- [ ] If `async=true`, publish to queue (Redis Streams / SQS / NATS)
- [ ] Return `job_id` immediately
- [ ] `GET /broker/jobs/{job_id}` to poll status
- [ ] Background worker processes queue and invokes agent

**2. Webhook Subscriptions** (Medium Priority)
- [ ] Add `webhooks` field to agent manifest:
  ```json
  "webhooks": {
    "on_invoke": "https://agent.com/webhook/invoke",
    "on_error": "https://agent.com/webhook/error"
  }
  ```
- [ ] Broker calls webhooks after invocation (success/error)
- [ ] Retry logic for failed webhook calls

**3. Event Pub/Sub** (Low Priority - Future)
- [ ] `POST /broker/publish` endpoint (publish events)
- [ ] `GET /broker/subscribe` (SSE/WebSocket for real-time feeds)
- [ ] Topic-based subscriptions (e.g., `agent:demo:translator:events`)

**4. Durable Queues for Orchestration** (Medium Priority)
- [ ] Use queues for longer-running orchestration tasks
- [ ] Job status tracking and polling

### Metrics to Track
- Broker success rate, retries, queue depth
- End-to-end latency (sync vs async)
- % of invocations using async vs sync
- Webhook delivery success rate

### Risks
- **Operational complexity**: Start with managed messaging (AWS SQS + SNS or Redis streams)
- **Cost**: Queue services add infrastructure cost
- **Reliability**: Need dead-letter queues, retry policies

---

## Prioritized Implementation Roadmap

### Week 0-1: Stabilize & Foundation
- [x] ✅ Basic embeddings (DONE)
- [x] ✅ Vector search (DONE)
- [ ] Add `vcv_version` fields to models
- [ ] Migration for VCV versioning

### Week 2: Enhanced Embeddings (MVP+)
- [ ] `POST /registry/agents/{agent_uuid}/refresh-vcv` endpoint
- [ ] Expose `vcv_version` in API responses
- [ ] **Defer**: Enhanced embedding content (nice to have)

### Week 3: Semantic Ranking (MVP)
- [ ] Add `metadata` field to `Capability` model
- [ ] Implement `RankingService` with configurable weights
- [ ] Convert `GET /registry/discover` to `POST /registry/discover` with filters
- [ ] Add `score`, `estimated_latency`, `estimated_cost` to responses

### Week 4: Trust & Metrics (High Priority)
- [ ] Create metrics computation (background job or materialized view)
- [ ] Implement `trust_score` calculation
- [ ] `GET /registry/agents/{agent_id}/metrics` endpoint
- [ ] Update trust_score periodically

### Week 5: Metrics Dashboard & Feedback
- [ ] Show basic metrics in responses
- [ ] `POST /registry/agents/{agent_id}/feedback` endpoint
- [ ] Admin verification endpoint (if needed)

### Week 6: Manual Orchestration (Medium Priority)
- [ ] Create `Orchestration` model
- [ ] `POST /broker/orchestrations` endpoint
- [ ] DAG execution engine (sequential + parallel)
- [ ] `GET /broker/orchestrations/{id}` status polling

### Week 7-8: Async & Pub/Sub (Medium Priority)
- [ ] Async invocation support (queue-based)
- [ ] Webhook subscriptions
- [ ] Job status polling
- [ ] Refine ranking weights based on usage data

---

## What NOT to Build (Low Priority / Defer)

### ❌ Defer to Later
1. **Enhanced embedding content** (user confirmed: "nice to have")
   - Including more metadata in embeddings can wait
   - Current embeddings are sufficient for MVP

2. **Automatic task decomposition** (Stage B from Pattern 3)
   - Manual DAG orchestration is sufficient for MVP
   - LLM-based decomposition can come later

3. **Advanced orchestration features** (Stage C)
   - Retry logic, cost optimization, parallel execution can wait
   - Start with simple sequential execution

4. **Full pub/sub event fabric** (Pattern 5 - advanced features)
   - Webhooks and async queues are sufficient
   - Full event streaming can come later

5. **Complex reputation graph** (Pattern 4 - advanced)
   - Basic trust_score is sufficient
   - Social graph, transitive trust can wait

---

## Critical Guardrails (Non-Negotiable)

### Must Implement Before Production

1. **Schema Validation**
   - ✅ Already have Pydantic schemas
   - [ ] Add JSON Schema validation for input/output schemas
   - [ ] Reject ambiguous capability definitions

2. **Circuit Breakers**
   - [ ] Per-agent invocation rate limiting
   - [ ] Per-orchestration depth limits
   - [ ] Total chain time cap (prevent infinite loops)

3. **Auth & Scoping**
   - ✅ Already have JWT auth
   - [ ] API key scoping by capability
   - [ ] Rate limiting per user/agent

4. **Input/Output Validation**
   - [ ] Enforce JSON Schema validation at broker layer
   - [ ] Validate against capability input_schema before invocation

5. **Billing / Quotas**
   - [ ] Simulate cost before invocation (if metadata available)
   - [ ] User-level quotas/limits
   - [ ] Cost tracking per invocation

6. **Loop Detection**
   - [ ] Maintain call stack trace in orchestration
   - [ ] Detect cycles in DAG
   - [ ] Prevent recursive agent calls

---

## Data Model Changes Summary

### New Tables/Models Needed
1. **AgentMetrics** (or computed view)
   - `agent_id`, `window_start`, `invocations`, `successes`, `avg_latency`, `total_cost`

2. **Orchestration**
   - `orchestrator_id`, `task_id`, `dag`, `status`, `results`, `created_at`, `updated_at`

3. **AgentFeedback** (optional)
   - `agent_id`, `user_id`, `rating`, `comment`, `created_at`

### Schema Updates
1. **Capability** model:
   - Add `metadata` JSONB field
   - Add `vcv_version` String field

2. **Agent** model:
   - Add `vcv_version` String field
   - Add `trust_score` Float field (computed/cached)

3. **InvocationLog** model:
   - ✅ Already has most fields needed
   - Consider adding `cost_usd` if tracking costs

---

## API Endpoints Summary

### New Endpoints to Add

**Registry:**
- `POST /registry/agents/{agent_uuid}/refresh-vcv` - Refresh embeddings
- `POST /registry/discover` - Enhanced discover with filters (keep GET for backward compat)
- `GET /registry/agents/{agent_id}/metrics` - Get agent metrics
- `POST /registry/agents/{agent_id}/feedback` - Submit feedback
- `PATCH /registry/agents/{agent_id}/verify` - Admin verification

**Broker:**
- `POST /broker/orchestrations` - Create orchestration
- `GET /broker/orchestrations/{id}` - Get orchestration status
- `GET /broker/jobs/{job_id}` - Get async job status (if async support added)

**Optional:**
- `POST /registry/decompose` - Advisory task decomposition (Stage B, later)

---

## Success Metrics

### Overall Network Health
- Agent registration rate
- Invocation success rate
- Average trust_score across network
- Number of active orchestrations

### User Experience
- Time to find matching agent (discover latency)
- Precision@5 of returned agents
- % of successful match→invoke flows
- Average orchestration completion time

### Technical Performance
- Embedding generation time
- Search/ranking latency
- Broker success rate
- Queue depth (if async)

---

## Next Steps

1. **Review this plan** with team
2. **Prioritize** based on user needs
3. **Start with Week 0-1** tasks (VCV versioning)
4. **Iterate** based on feedback and usage patterns

---

## Notes

- **Embedding enhancement** is explicitly marked as "nice to have" per user
- **Orchestration** can start simple (manual DAGs) and evolve
- **Trust scores** are critical for ranking but can start with basic computation
- **Async pub/sub** is nice-to-have; sync broker is sufficient for MVP
- All features should be **backward compatible** where possible

