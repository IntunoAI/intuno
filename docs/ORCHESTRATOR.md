# Orchestrator Plan: Intelligent Task Completion

## 1. Overview

The **Orchestrator** is the server-side component that **completes tasks** for clients. The client sends a goal and input; the orchestrator is responsible for planning, agent selection, and execution. It lives in the **same application** as Registry and Broker and follows the existing codebase patterns (routes → services → repositories). Scaling is **vertical** (single process); no separate orchestrator service or message bus for MVP.

### Principles

- **Same pattern as today**: Routes, services, repositories, schemas; solo-dev friendly, single deployable.
- **Intelligence on the server**: Planning and agent selection are done by the orchestrator, not the client.
- **Broker stays dumb**: Orchestrator uses Broker for every agent call; Broker remains a 1:1 invoke pipe.
- **Edge cases and fallbacks** are designed in from the start (see below).

---

## 2. Architecture (In-Process, Vertical Scaling)

### 2.1 Placement

- **No new service.** Orchestrator is a new domain inside the existing app. See **§2.3 File layout and symmetry** for the exact mapping of route, service, schema, model, repository, and utilities.

### 2.2 Data Flow

1. Client → `POST /tasks` (goal + input + optional conversation_id, message_id). See §2.3 for route prefix.
2. Task service creates a **Task** (DB), status `pending` → `running`.
3. **Planner** produces a plan (single step or multiple steps; see Execution Model).
4. **Executor** runs each step: discover (Registry) → select agent/capability → invoke (Broker) → collect result.
5. If a step fails: retry and/or fallback (e.g. generalist); see §6.
6. Task status → `completed` or `failed`; result or error stored.
7. Response: sync (return result) or async (return `task_id`, client polls `GET /tasks/{task_id}`; see §2.3 for route prefix).

### 2.3 File layout and symmetry

We follow the same pattern as the rest of the app: **one domain = one route file, one service file, one schema file, one model file, one repository file**. Components that have **no HTTP surface** (no route) live in **utilities**.

**Domain naming choice:** The resource we create and poll is a **Task**. We can name the domain either **task** or **orchestrator**:

| Option | Route file | Prefix | Service | Schema | Model | Repository | Result |
|--------|------------|--------|---------|--------|-------|------------|--------|
| **A – domain = task** | `routes/task.py` | `/tasks` | `services/task.py` | `schemas/task.py` | `models/task.py` | `repositories/task.py` | Full symmetry: same name in every layer. |
| **B – domain = orchestrator** | `routes/orchestrator.py` | `/orchestrator` | `services/orchestrator.py` | `schemas/orchestrator.py` | `models/task.py` | `repositories/task.py` | Entity is Task; URL and service say “orchestrator”. |

**Chosen: task domain.** We use **task** as the domain name everywhere for symmetry: `task` everywhere. API: `POST /tasks`, `GET /tasks/{task_id}`. The “orchestrator” is the behaviour (the service that plans and runs steps), not the URL — but the orchestrator *logic* can still live in code (see below).

**We didn’t get rid of the orchestrator.** We only chose "task" as the *domain name* for files. The **orchestrator** is the behaviour: "take a goal, plan steps, execute steps, return result." That behaviour can live in the task service only (TaskService calls Planner + Executor directly), or **in utilities as a coordinator (recommended):** add `utilities/orchestrator.py` — a thin coordinator that does "plan then execute." It has no route and no persistence, so it fits utilities (like planner and executor). TaskService then: create task → call `orchestrator.run(goal, input, context)` → write result back to task. So "orchestrator" has a clear home in code; not too complex (orchestrator.py can be a small module that calls planner then executor).

**Planner, Executor, and (optionally) Orchestrator – utilities only.** They do not expose routes; they are used by the task service. So they live in `utilities/`, like `embedding.py` and `semantic_enhancement.py`:

- `src/utilities/planner.py` – plan generation (goal + input → list of steps or DAG).
- `src/utilities/executor.py` – step execution (calls Registry + Broker, handles retries/fallback).
- `src/utilities/orchestrator.py` – *(recommended)* coordinates plan + execute; single entry point for "run this goal" (uses Planner and Executor).

**Resulting layout:**

```
src/
  routes/task.py           # POST /tasks, GET /tasks/{task_id}
  services/task.py         # TaskService (create/update task, call Orchestrator utility, persist result)
  schemas/task.py          # TaskCreate, TaskResponse, TaskListResponse, etc.
  models/task.py           # Task (and optionally TaskStep)
  repositories/task.py     # TaskRepository
  utilities/
    planner.py             # Planner – no route
    executor.py            # Executor – no route
    orchestrator.py        # Orchestrator – no route; composes Planner + Executor (recommended)
```

**Dependencies:** TaskService depends on TaskRepository and **Orchestrator** (utility). Orchestrator depends on Planner, Executor, RegistryService, BrokerService. Same DI pattern as today (FastAPI `Depends()`). If you skip `orchestrator.py`, TaskService depends on Planner, Executor, RegistryService, BrokerService, TaskRepository directly.

---

## 3. Execution Model: Sequential vs Concurrent vs Parallel

### 3.1 Options

| Model        | Description                    | When steps run              | Use case                          |
|-------------|--------------------------------|-----------------------------|-----------------------------------|
| **Sequential** | One step after another        | Step N+1 after step N       | Steps depend on previous outputs  |
| **Concurrent** | Multiple steps in flight      | asyncio tasks, single process | I/O-bound; no true CPU parallelism |
| **Parallel**   | Multiple steps on multiple CPUs | Multiprocessing / workers  | CPU-heavy steps (rare for agents)  |

### 3.2 Execution for MVP: start simple, then add complexity

- **Start with simple sequential execution.**  
  - Steps are ordered (list or DAG); each step’s input can depend on prior steps’ outputs.  
  - Simple to reason about, easy to debug, and matches “pipeline” tasks (e.g. extract → translate → summarize).

- **Concurrency (later).** When we add it: if the plan marks steps as independent (e.g. `depends_on: []`), the executor can run those steps concurrently via `asyncio.gather()`. **No parallel (multiprocessing)** for MVP: agent calls are I/O-bound; asyncio is enough.  

### 3.3 Edge Cases (Execution)

- **Single-step task**: One step; no ordering or concurrency needed.
- **Empty plan**: Treated as failure (no steps to run).
- **Step timeout**: Per-step timeout (e.g. via Broker config); on timeout, step fails → retry or fallback, then task fails if no recovery. **Task timeout**: see §3.4.
- **Partial failure**: If a step fails and no fallback succeeds, task fails; previous step results can be stored for debugging/retry.
- **Cycle in plan**: Plan validation must reject cycles (DAG only); executor assumes acyclic dependency graph.

### 3.4 Task timeout (configurable from settings)

- **Task-level timeout** is configurable from application settings (e.g. `TASK_TIMEOUT_SECONDS` in `src/core/settings.py`). Default can be e.g. 60 seconds.
- If the task runs longer than this, the executor stops and the task is marked `failed` (or `timeout` if we add that status). Behaviour: fail the task; no cancel/resume for MVP.
- Use this value when starting the task (e.g. pass to orchestrator/executor so they can enforce it). Can adjust later (e.g. per-integration override).

---

## 4. Internal Queues and Polling (Step Status)

### 4.1 Do we need queues?

- **MVP: no internal job queue.**  
  - Task runs in the same request (sync) or in a single background task (e.g. `asyncio.create_task` or FastAPI background) that runs the plan to completion.  
  - Steps are executed in-process; “step status” is just in-memory state (and persisted on the Task model at the end, or per step if we store step results).

- **Why no queue for now:**  
  - Solo dev, vertical scaling; fewer moving parts.  
  - No durability requirement for “resume after crash” in MVP.  
  - If the process dies, the task can be marked `failed` or `timeout`; client can retry by creating a new task.

**Cron-ready code (no cron yet).** Do not implement the cron job itself yet, but have the code ready so a future cron can easily work on stale/failed tasks. Expose e.g. TaskRepository: `get_stale_running_tasks(older_than_minutes: int)` (returns tasks with status `running` and `updated_at` older than threshold) and TaskService or repository: `mark_stale_tasks_timeout()` (marks those tasks as `timeout` or `failed`). A future cron can call these; no scheduler in this repo for MVP.

### 4.2 Step status visibility

- **Option A – No per-step polling:**  
  - Client only polls **task** status: `pending | running | completed | failed`.  
  - Step details (and any “step status”) are optional in the task response (e.g. `steps: [{ step_id, status, result }]` when task is completed or failed).  
  - Simple; good for MVP.

- **Option B – Per-step status in task payload:**  
  - While task is `running`, task payload can include `steps: [{ step_id, status: pending|running|completed|failed }]`.  
  - No separate “step status” API; just one `GET /tasks/{task_id}` that returns task + steps.  
  - Orchestrator updates the task document (or step rows) as it goes; client polls the same endpoint.

**Chosen: Option B.** Per-step status in the **response body** only (no separate step endpoints). One GET for the task; body includes current step statuses and, when done, step results. No internal queue; updates are in-memory + DB writes after each step (or at end) so that polling sees progress.

### 4.3 Later: durable queue (optional)

- If later you need durability (e.g. long-running tasks, restart-safe work): introduce a **task queue** (e.g. Celery, ARQ, or a small PostgreSQL-based queue).  
- Then: `POST /tasks` enqueues a job; a worker runs the executor; step state is persisted so that “step status” and “resume” are possible.  
- Document this as a future extension; not required for MVP.

---

## 5. Edge Cases (Summary)

| Edge case | Handling |
|-----------|----------|
| **No agents found for a step** | Use configured fallback (e.g. generalist agent); see §6. |
| **Discovery returns zero results** | Fallback agent/capability; if none configured, task fails with clear error. |
| **Agent/capability fails at runtime** | Retry (Broker retries) then step-level retry; then fallback; then mark task failed. |
| **Timeout (task or step)** | Step timeout via Broker; task-level timeout optional; on timeout → fail step/task. |
| **Empty or invalid plan** | Validation: reject empty plan; invalid DAG (e.g. cycle) → 400. |
| **Conversation/message context** | Same as Broker: optional conversation_id/message_id; validated; passed to Broker for attribution. |
| **Quota exceeded mid-task** | Broker returns 429; orchestrator marks step failed and can fail task or try fallback (if fallback has quota). |
| **Process crash mid-task** | No queue: task may be stuck `running`. Code ready for cron (e.g. `get_stale_running_tasks`, `mark_stale_tasks_timeout`); no cron job yet (see §4.1). |
| **Idempotency** | Chosen: `Idempotency-Key` header on `POST /tasks`; store on task; return existing task if same key (same user/integration). Can adjust later (see §8). |
| **Very long task** | Prefer async: return 202 + task_id; client polls. Task-level timeout recommended. |

---

## 6. Fallback: Generalist / In-House Agent When Discovery Is Not Enough

### 6.1 Problem

- Discovery (semantic or keyword) might return **no agents** or **no suitable capability** for a step.  
- We do not want to fail the task immediately if a “good enough” generalist can attempt it.

### 6.2 Where the generalist lives (not in this project)

The **generalist** (or any “in-house” fallback) is **not** part of this (wisdom) codebase. The idea:

- **This project** = Intuno platform: Registry, Broker, Task (orchestrator), Auth, etc. It does not host agent implementations.
- **Separate FastAPI app(s)** = your own agent runtime(s). You build **topic-specific agents** (e.g. 10–15 at launch) and deploy them in **another** FastAPI service. Each agent exposes an invoke endpoint; you **register** those agents (manifests + endpoints) in this app’s **Registry**.
- **Fallback** = one of those registered agents (or a dedicated “generalist” agent in that same external app) is configured as the orchestrator’s fallback. When discovery returns no candidates, the orchestrator invokes that agent via the **Broker** like any other agent.

So: generalist = in-house agent by **ownership** and **deployment**, but by **contract** it’s just another registered agent. This project stays a platform; agent code stays in your other repo(s).

### 6.3 Approach: Configurable Fallback Agent

- **Configuration**: Allow a **fallback** agent (and optionally capability) to be configured at:
  - **Integration level** (e.g. per API key / integration), or  
  - **Global level** (e.g. in settings).  

- **Semantics**:  
  - “Generalist” = a **registered** agent (and optionally a capability) that accepts broad input (e.g. natural language goal + raw input) and tries to complete the step.  
  - It is deployed in your **separate** FastAPI app (e.g. one of your 10–15 topic-specific agents, or a dedicated generalist capability like `handle_generic_request`). It is registered here so the Broker can invoke it.

### 6.4 When to Use Fallback

1. **Discovery returns no candidates** for the step.  
2. **Discovery returns candidates but all fail** (after retries) for that step.  
3. Optionally: **Discovery returns fewer than N candidates** (e.g. you require at least one specialist; if zero, use fallback).

Do **not** use fallback when discovery already returned a healthy result and an agent failed transiently; use retries first, then optionally fallback for that step.

### 6.5 Configuration Shape (Example)

- Global: `settings.ORCHESTRATOR_FALLBACK_AGENT_ID` (and optionally `ORCHESTRATOR_FALLBACK_CAPABILITY_ID`).  
- Per-integration: `BrokerConfig` or new `OrchestratorConfig`: `fallback_agent_id`, `fallback_capability_id`.  
- If not set, no fallback: “no agents found” → task fails with a clear error (e.g. “No suitable agent found for step X; consider configuring a fallback agent”).

### 6.6 Edge Cases (Fallback)

- **Fallback agent itself fails**: Treat like any other step failure (retry, then fail task).  
- **Fallback not configured**: Return explicit error: “No agents found and no fallback configured.”  
- **Fallback not in allowlist**: If integration has an allowlist (Broker), fallback agent must be in it or fallback is skipped (and task fails).

---

## 7. What We Do Not Introduce (MVP)

- Separate orchestrator microservice.
- **Agent implementations in this repo.** Agents (including the generalist) live in a separate FastAPI app; this app only registers and invokes them via Registry + Broker (see §6.2).  
- Internal message queue or job queue (run in-process / background task only).  
- Multiprocessing / parallel step execution.  
- Client-submitted DAGs (plan is always server-generated).  
- Automatic “retry with different agent” from a large pool (only retries + single fallback).

---

## 8. Decided and Open Items

**Decided:**

- **Task domain** – We use task everywhere (route, service, schema, model, repository); see §2.3.
- **Step status** – Option B: per-step status in task payload; see §4.2.
- **Task timeout** – Configurable from settings (e.g. `TASK_TIMEOUT_SECONDS`); see §3.4.
- **Execution** – Start with simple sequential tasks; add concurrent/DAG later; see §3.2.
- **Cron for stale tasks** – Do not implement the cron job yet; expose code (e.g. `get_stale_running_tasks`, `mark_stale_tasks_timeout`) so a future cron can call it; see §4.1.
- **Idempotency** – Use `Idempotency-Key` header on `POST /tasks`. Store the key on the task; if the same key is sent again (same user/integration), return the existing task instead of creating a new one. Can adjust later (e.g. add body field, TTL).

**Open (to revisit):**

- **Plan representation**: Flat list of steps vs explicit DAG (nodes + edges). Start with flat list; DAG when we add concurrency.