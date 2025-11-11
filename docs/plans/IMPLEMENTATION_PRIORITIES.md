# Implementation Priorities - Federation of Agents Patterns

## Quick Reference: What to Build vs What to Skip

### ✅ **BUILD NOW (MVP - Weeks 2-5)**

#### 1. VCV Versioning & Refresh (Week 2)
- Add `vcv_version` to Agent and Capability models
- `POST /registry/agents/{uuid}/refresh-vcv` endpoint
- **Why**: Needed for embedding model upgrades
- **Effort**: Low
- **Impact**: High (future-proofing)

#### 2. Semantic Ranking with Metadata (Week 3) ⭐ **CRITICAL**
- Add `metadata` JSONB to Capability (cost, latency hints)
- Implement ranking function: `score = α*similarity + β*latency + γ*cost + δ*trust`
- Convert `GET /registry/discover` → `POST /registry/discover` with filters
- **Why**: Core differentiator - makes discovery actually useful
- **Effort**: Medium
- **Impact**: Very High

#### 3. Trust Scores & Metrics (Week 4-5) ⭐ **CRITICAL**
- Compute rolling metrics: `success_rate_7d`, `avg_latency_7d`
- Calculate `trust_score` (0.0-1.0) from metrics + verification badge
- `GET /registry/agents/{id}/metrics` endpoint
- **Why**: Essential for ranking and filtering low-quality agents
- **Effort**: Medium
- **Impact**: Very High

---

### ⚠️ **BUILD LATER (Weeks 6-8)**

#### 4. Manual Orchestration (Week 6)
- DAG model and execution engine
- `POST /broker/orchestrations` endpoint
- **Why**: Enables multi-agent workflows
- **Effort**: High
- **Impact**: Medium (nice to have for complex use cases)

#### 5. Async Pub/Sub (Week 7-8)
- Async invocation via queues
- Webhook subscriptions
- **Why**: Better for long-running tasks
- **Effort**: High
- **Impact**: Medium (sync broker works for MVP)

---

### ❌ **SKIP / DEFER (Not Priority)**

#### 1. Enhanced Embedding Content
- Including more metadata (cost, latency) in embedding text
- **Why Skip**: User confirmed this is "nice to have"
- **Current State**: Basic embeddings work fine
- **When to Revisit**: If search quality degrades

#### 2. Automatic Task Decomposition
- LLM-based decomposition helper (`POST /registry/decompose`)
- **Why Skip**: Manual DAGs are sufficient for MVP
- **When to Revisit**: If users request it

#### 3. Advanced Orchestration Features
- Automatic retry, cost optimization, parallel execution
- **Why Skip**: Start simple, add complexity later
- **When to Revisit**: After manual orchestration proves useful

#### 4. Full Event Streaming
- Pub/sub event fabric with topics
- **Why Skip**: Webhooks + async queues are enough
- **When to Revisit**: If real-time events become critical

#### 5. Complex Reputation Graph
- Social graph, transitive trust, community ratings
- **Why Skip**: Basic trust_score is sufficient
- **When to Revisit**: If network grows large

---

## Priority Matrix

| Feature | Priority | Effort | Impact | Week |
|---------|----------|--------|--------|------|
| VCV Versioning | High | Low | High | 2 |
| **Semantic Ranking** | **Critical** | Medium | **Very High** | 3 |
| **Trust Scores** | **Critical** | Medium | **Very High** | 4-5 |
| Manual Orchestration | Medium | High | Medium | 6 |
| Async Pub/Sub | Medium | High | Medium | 7-8 |
| Enhanced Embeddings | Low | Low | Low | Defer |
| Auto Decomposition | Low | High | Low | Defer |

---

## Must-Have Before Production

### Security & Reliability
- [ ] Circuit breakers (rate limits, depth limits)
- [ ] Input/output schema validation at broker
- [ ] Loop detection in orchestrations
- [ ] Cost simulation before invocation

### Already Done ✅
- [x] JWT authentication
- [x] Basic invocation logging
- [x] Schema validation (Pydantic)

---

## Recommended Implementation Order

### Phase 1: Foundation (Weeks 2-3)
1. VCV versioning (Week 2)
2. **Semantic ranking with metadata** (Week 3) ⭐

### Phase 2: Trust & Quality (Weeks 4-5)
3. **Trust scores & metrics** (Week 4-5) ⭐

### Phase 3: Advanced Features (Weeks 6-8)
4. Manual orchestration (Week 6)
5. Async pub/sub (Week 7-8)

### Phase 4: Polish (Later)
6. Enhanced embeddings (if needed)
7. Auto decomposition (if requested)
8. Advanced orchestration (if needed)

---

## Key Decisions Made

1. **Embedding enhancement = Defer**
   - User confirmed: "nice to have"
   - Current embeddings sufficient for MVP

2. **Ranking = Critical**
   - Without ranking, discovery is just keyword search
   - Metadata filters essential for production use

3. **Trust scores = Critical**
   - Prevents spam/low-quality agents
   - Essential for ranking function

4. **Orchestration = Medium Priority**
   - Manual DAGs first, auto-decomposition later
   - Start simple, add complexity incrementally

5. **Async = Medium Priority**
   - Sync broker works for MVP
   - Add async when needed for long-running tasks

---

## Questions to Answer

1. **Cost tracking**: Do we want to track actual costs per invocation, or just use metadata hints?
   - **Recommendation**: Start with metadata hints, add actual tracking later

2. **Trust score weights**: How should we weight success_rate vs latency vs verification?
   - **Recommendation**: Default weights, make configurable later

3. **Orchestration complexity**: How deep should DAGs be allowed?
   - **Recommendation**: Start with max depth of 10, make configurable

4. **Backward compatibility**: Keep GET /registry/discover?
   - **Recommendation**: Yes, deprecate after POST is stable

---

## Success Criteria

### MVP Success (Weeks 2-5)
- ✅ Agents can be discovered via semantic search with ranking
- ✅ Trust scores filter out low-quality agents
- ✅ Metadata (cost, latency) influences ranking
- ✅ VCV versioning allows embedding model upgrades

### Full Success (Weeks 6-8)
- ✅ Multi-agent workflows via orchestration
- ✅ Async invocations for long-running tasks
- ✅ Webhook subscriptions for event-driven flows

---

## Next Action Items

1. **This Week**: Review plan with team, get approval
2. **Week 2**: Start VCV versioning implementation
3. **Week 3**: Implement semantic ranking (highest priority)
4. **Week 4**: Begin trust score computation

---

## Notes

- All new features should be **backward compatible**
- Use **feature flags** for gradual rollout
- **Monitor metrics** from day 1 (invocation success rate, search latency, etc.)
- **Iterate** based on real usage patterns, not just theory

