# How the Embedding System Works

## Overview

The system uses a **dual-embedding strategy** with **capability-level search** for precise matching. Here's how it all works:

```
┌─────────────────────────────────────────────────────────────┐
│                    EMBEDDING ARCHITECTURE                    │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  PostgreSQL (Metadata)          Qdrant (Vectors)             │
│  ┌──────────────┐              ┌──────────────┐            │
│  │   Agents     │              │   agents      │            │
│  │ - agent_id   │◄─────────────│  collection   │            │
│  │ - name       │              │ - vector       │            │
│  │ - qdrant_id  │              │ - payload      │            │
│  │ - emb_version│              │ - version      │            │
│  └──────┬───────┘              └──────────────┘            │
│         │                                                     │
│         │ 1:N                                                 │
│         ▼                                                     │
│  ┌──────────────┐              ┌──────────────┐            │
│  │ Capabilities │              │ capabilities │            │
│  │ - capability │◄─────────────│  collection   │            │
│  │ - input_schema│             │ - vector      │            │
│  │ - qdrant_id  │              │ - payload     │            │
│  │ - emb_version│              │ - agent_uuid   │            │
│  └──────────────┘              └──────────────┘            │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 1. Agent Registration Flow

When you register an agent, here's what happens step-by-step:

### Step 1: Generate Agent Embedding

```python
# Example manifest:
{
  "agent_id": "agent:demo:calculator:1.0.0",
  "name": "Calculator Agent",
  "description": "Performs basic math operations",
  "tags": ["math", "calculator"],
  "capabilities": [
    {
      "id": "add",
      "input_schema": {
        "type": "object",
        "properties": {
          "a": {"type": "number", "description": "First number"},
          "b": {"type": "number", "description": "Second number"}
        },
        "required": ["a", "b"]
      }
    }
  ]
}
```

**Text Preparation:**
- If `enhance_manifest=False` (default): 
  ```
  "Calculator Agent. Performs basic math operations. Tags: math, calculator"
  ```
- If `enhance_manifest=True`: LLM enhances this text first

**Embedding Generation:**
- OpenAI `text-embedding-3-small` model
- Creates 1536-dimensional vector
- Stored with version `"1.0"` (from `EMBEDDING_VERSION` setting)

### Step 2: Store Agent in Database

```python
Agent(
  agent_id="agent:demo:calculator:1.0.0",
  name="Calculator Agent",
  qdrant_point_id=None,  # Will be set after Qdrant storage
  embedding_version="1.0"
)
```

### Step 3: Store Agent Embedding in Qdrant

**Collection:** `"agents"`

```python
Point(
  id=agent.uuid,  # e.g., "550e8400-e29b-41d4-a716-446655440000"
  vector=[0.123, -0.456, ...],  # 1536 dimensions
  payload={
    "agent_id": "agent:demo:calculator:1.0.0",
    "name": "Calculator Agent",
    "is_active": True,
    "embedding_version": "1.0"
  }
)
```

### Step 4: Generate Capability Embeddings

For each capability, the system extracts **comprehensive schema information**:

**Input Schema Extraction:**
```python
# From JSON schema:
{
  "properties": {
    "a": {"type": "number", "description": "First number"},
    "b": {"type": "number", "description": "Second number"}
  },
  "required": ["a", "b"]
}

# Becomes text:
"Capability: add. Input description: Adds two numbers. 
Input parameters: a (number, required): First number, 
b (number, required): Second number. 
Output description: The sum. 
Output: result (number): The calculated sum"
```

**Key Improvements:**
- ✅ Extracts property names, types, descriptions
- ✅ Marks required vs optional fields
- ✅ Includes enum values if present
- ✅ Captures full schema structure

### Step 5: Store Capability Embeddings

**Collection:** `"capabilities"` (separate from agents!)

```python
Point(
  id=capability.uuid,  # Capability's database UUID
  vector=[0.789, -0.234, ...],  # 1536 dimensions
  payload={
    "agent_id": "agent:demo:calculator:1.0.0",
    "agent_uuid": "550e8400-...",  # Links back to agent
    "capability_id": "add",
    "agent_name": "Calculator Agent",
    "is_active": True,
    "embedding_version": "1.0"
  }
)
```

### Step 6: Link Everything Together

```python
# Update database records with Qdrant IDs
agent.qdrant_point_id = agent.uuid
capability.qdrant_point_id = capability.uuid
```

**Final State:**
- ✅ Agent in PostgreSQL with `qdrant_point_id`
- ✅ Agent embedding in Qdrant `"agents"` collection
- ✅ Capabilities in PostgreSQL with `qdrant_point_id`
- ✅ Capability embeddings in Qdrant `"capabilities"` collection
- ✅ All linked via UUIDs and payload metadata

---

## 2. Discovery/Search Flow

When you search for agents, here's the intelligent flow:

### Step 1: Query Processing

```python
# User query: "I need to add two numbers"
query = "I need to add two numbers"

# Optional: Enhance query with LLM (default: False)
if enhance_query:
    query = await llm_enhance(query)  # Expands with synonyms

# Generate query embedding
query_embedding = await generate_embedding(query)
# Result: [0.456, -0.789, ...]  # 1536 dimensions
```

### Step 2: Search Capabilities First (Primary Strategy)

**Why capabilities first?**
- More precise matching
- "add two numbers" matches the "add" capability, not the entire agent
- Better ranking by specific functionality

```python
# Search capabilities collection
capability_results = await qdrant.search_capabilities(
    query_vector=query_embedding,
    limit=30,  # Get more matches (3x requested limit)
    similarity_threshold=0.5,  # Optional distance threshold
    filter_conditions={"is_active": True}
)
```

**Qdrant Returns:**
```python
[
  {
    "id": "cap-uuid-1",
    "distance": 0.12,  # Very similar!
    "payload": {
      "agent_uuid": "550e8400-...",
      "capability_id": "add",
      "agent_name": "Calculator Agent",
      ...
    }
  },
  {
    "id": "cap-uuid-2",
    "distance": 0.45,
    "payload": {
      "agent_uuid": "550e8400-...",
      "capability_id": "multiply",
      ...
    }
  },
  ...
]
```

### Step 3: Aggregate to Agents

**Group by agent, keep best match:**

```python
agent_scores = {}  # agent_uuid -> best_distance

for cap_result in capability_results:
    agent_uuid = cap_result["payload"]["agent_uuid"]
    distance = cap_result["distance"]
    
    # Keep the BEST (lowest distance) capability match per agent
    if agent_uuid not in agent_scores or distance < agent_scores[agent_uuid]:
        agent_scores[agent_uuid] = distance

# Result:
# {
#   "550e8400-...": 0.12,  # Calculator Agent (best match: "add")
#   "660e8400-...": 0.34,  # Math Helper Agent
# }
```

**Why this works:**
- If an agent has multiple capabilities, we use the **best matching one**
- Agent is ranked by its **most relevant capability**
- More accurate than averaging all capabilities

### Step 4: Sort and Limit

```python
# Sort by distance (lower = better)
sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1])[:10]

# Result: [(agent_uuid_1, 0.12), (agent_uuid_2, 0.34), ...]
```

### Step 5: Fetch Full Agent Data

```python
# Get agent UUIDs
agent_ids = [uuid for uuid, _ in sorted_agents]

# Fetch from PostgreSQL with relationships
agents = await db.query(Agent).where(Agent.id.in_(agent_ids))
# Includes: capabilities, requirements, etc.

# Return with similarity scores
return [
    (agent, agent_scores[agent.id])
    for agent in agents
]
```

### Step 6: Fallback to Agent-Level Search

**If no capability matches found:**

```python
if not capability_results:
    # Fallback: search agent embeddings directly
    agent_results = await qdrant.search_similar(
        query_vector=query_embedding,
        limit=10,
        collection_name="agents"
    )
    # Returns agents directly
```

---

## 3. Embedding Versioning

### Why Versioning?

Embedding structure can evolve:
- Add new fields to text preparation
- Change how schemas are extracted
- Update embedding model
- Modify aggregation strategy

### How It Works

**Current Version:**
```python
# In settings.py
EMBEDDING_VERSION = "1.0"
```

**Stored Everywhere:**
- Agent model: `agent.embedding_version = "1.0"`
- Capability model: `capability.embedding_version = "1.0"`
- Qdrant payload: `{"embedding_version": "1.0"}`

**Future Evolution:**
```python
# When you change the structure:
EMBEDDING_VERSION = "2.0"  # New version

# New registrations use 2.0
# Old agents still have 1.0

# You can identify and re-embed old agents:
for agent in agents:
    if agent.embedding_version != settings.EMBEDDING_VERSION:
        # Re-embed with new structure
        await update_agent(agent, ...)
```

---

## 4. Key Improvements Over Old System

### Before (Old System)
```
❌ Single agent embedding (blends all capabilities)
❌ Capability embeddings generated but NOT stored
❌ LLM enhancement always on (slow, expensive)
❌ Simple text: "add. Input: number. Output: number"
❌ No versioning
```

### After (New System)
```
✅ Dual embeddings: agent + capabilities
✅ Capability embeddings stored in separate collection
✅ LLM enhancement optional (default: off)
✅ Rich text: extracts full schema details
✅ Version tracking for future evolution
✅ Capability-first search for precision
```

---

## 5. Example: Complete Flow

### Registration Example

```python
# 1. Register agent
manifest = {
    "agent_id": "agent:demo:calculator:1.0.0",
    "name": "Calculator Agent",
    "description": "Performs math operations",
    "capabilities": [
        {"id": "add", "input_schema": {...}},
        {"id": "multiply", "input_schema": {...}}
    ]
}

agent = await registry_service.register_agent(manifest, user_id)

# What happens:
# ✅ Agent embedding created → stored in Qdrant "agents" collection
# ✅ "add" capability embedding created → stored in Qdrant "capabilities" collection
# ✅ "multiply" capability embedding created → stored in Qdrant "capabilities" collection
# ✅ All linked via UUIDs and metadata
```

### Search Example

```python
# 2. Search for agents
query = "I need to add numbers"

results = await registry_service.semantic_discover(
    DiscoverQuery(query=query, limit=5)
)

# What happens:
# ✅ Query → embedding: [0.456, -0.789, ...]
# ✅ Search "capabilities" collection → finds "add" capability (distance: 0.12)
# ✅ Aggregate to agent → Calculator Agent (best match: 0.12)
# ✅ Return: [(Calculator Agent, 0.12), ...]
```

---

## 6. Data Flow Diagram

```
REGISTRATION:
┌─────────────┐
│   Manifest   │
└──────┬───────┘
       │
       ▼
┌─────────────────┐      ┌──────────────┐
│ Generate Agent  │─────▶│   Qdrant     │
│   Embedding     │      │ "agents"      │
└─────────────────┘      └──────────────┘
       │
       ▼
┌─────────────────┐      ┌──────────────┐
│ Generate Cap    │─────▶│   Qdrant     │
│   Embeddings    │      │"capabilities"│
└─────────────────┘      └──────────────┘
       │
       ▼
┌─────────────────┐
│  PostgreSQL     │
│  (Metadata)     │
└─────────────────┘

DISCOVERY:
┌─────────────┐
│   Query     │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ Query Embedding │
└──────┬──────────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ Search       │  │ Search       │
│ Capabilities │  │ Agents       │
│ (Primary)    │  │ (Fallback)   │
└──────┬───────┘  └──────┬───────┘
       │                 │
       └────────┬────────┘
                │
                ▼
         ┌──────────────┐
         │  Aggregate    │
         │  to Agents    │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │   Fetch      │
         │   from DB    │
         └──────┬───────┘
                │
                ▼
         ┌──────────────┐
         │   Return     │
         │   Results    │
         └──────────────┘
```

---

## 7. Configuration

### Settings

```python
# src/core/settings.py

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"  # OpenAI model

# Embedding version (for structure evolution)
EMBEDDING_VERSION = "1.0"

# LLM enhancement (optional, default: False)
ENABLE_LLM_ENHANCEMENT = False  # Set to True if you want LLM enhancement
```

### Qdrant Collections

```python
# Two separate collections:
AGENTS_COLLECTION = "agents"           # Agent-level embeddings
CAPABILITIES_COLLECTION = "capabilities"  # Capability-level embeddings
```

---

## Summary

**The system now:**
1. ✅ Stores **both** agent and capability embeddings
2. ✅ Searches **capabilities first** for precision
3. ✅ Extracts **full schema details** for better matching
4. ✅ Tracks **embedding versions** for future evolution
5. ✅ Uses **optional LLM enhancement** (default: off)
6. ✅ **Aggregates** capability matches to agents intelligently

**Result:** Faster, cheaper, more precise semantic search! 🎯
