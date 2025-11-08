# Agent Registration Issue Summary

## Problem
The demo workflow is returning 422 Unprocessable Entity errors when trying to invoke agents through the `/broker/invoke` endpoint.

## Root Cause Analysis

### 1. Field Name Mismatch (FIXED)
- **Issue**: Demo workflow JavaScript was sending `agent` and `capability` instead of `agent_id` and `capability_id`
- **Fix Applied**: Updated `src/static/index.html` demo workflow to use correct field names
- **Status**: ✅ Fixed

### 2. Missing Invoke Endpoints (MAIN ISSUE)
- **Issue**: All registered agents have `invoke_endpoint: null` in the database
- **Root Cause**: Agents were registered before mock agents were running, so endpoints weren't available
- **Impact**: Broker service fails when trying to invoke agents because it can't find the endpoint

### 3. Schema Issues (PARTIALLY FIXED)
- **Issue**: `AgentListResponse` schema didn't include `invoke_endpoint` field
- **Fix Applied**: Added `invoke_endpoint: Optional[str] = None` to schema
- **Status**: ✅ Fixed

## Current State

### Mock Agents
- **Status**: ✅ Running on ports 8001-8004
- **Endpoints**:
  - PDF Summarizer: `http://localhost:8001/invoke`
  - Translator: `http://localhost:8002/invoke`
  - Scheduler: `http://localhost:8003/invoke`
  - Weather: `http://localhost:8004/invoke`

### Database State
- **Agents Registered**: ✅ 4 agents registered
- **Invoke Endpoints**: ❌ All set to `null`
- **Capabilities**: ✅ Properly registered

### API State
- **Registry API**: ✅ Working (with null endpoints)
- **Broker API**: ❌ Failing due to null endpoints
- **Authentication**: ✅ Working

## Required CLI Tool Features

### 1. Agent Registration CLI
```bash
# Register agents with proper endpoints
python cli.py register-agents --endpoints-file endpoints.json

# Or register individual agent
python cli.py register-agent \
  --agent-id "agent:demo:translator:1.0.0" \
  --endpoint "http://localhost:8002/invoke"
```

### 2. Endpoint Update CLI
```bash
# Update existing agents with endpoints
python cli.py update-endpoints --endpoints-file endpoints.json

# Or update individual agent
python cli.py update-endpoint \
  --agent-id "agent:demo:translator:1.0.0" \
  --endpoint "http://localhost:8002/invoke"
```

### 3. Agent Management CLI
```bash
# List all agents with their endpoints
python cli.py list-agents

# Check agent status
python cli.py check-agent --agent-id "agent:demo:translator:1.0.0"

# Test agent invocation
python cli.py test-agent \
  --agent-id "agent:demo:translator:1.0.0" \
  --capability "translate_text" \
  --input '{"text": "Hello", "target_lang": "es"}'
```

## Endpoints Configuration

### endpoints.json
```json
{
  "agents": [
    {
      "agent_id": "agent:demo:pdf_summarizer:1.0.0",
      "invoke_endpoint": "http://localhost:8001/invoke"
    },
    {
      "agent_id": "agent:demo:translator:1.0.0", 
      "invoke_endpoint": "http://localhost:8002/invoke"
    },
    {
      "agent_id": "agent:demo:scheduler:1.0.0",
      "invoke_endpoint": "http://localhost:8003/invoke"
    },
    {
      "agent_id": "agent:demo:weather:1.0.0",
      "invoke_endpoint": "http://localhost:8004/invoke"
    }
  ]
}
```

## Database Schema Requirements

### Agent Model
```python
class Agent(BaseModel):
    agent_id: str
    invoke_endpoint: str  # This should NOT be null
    # ... other fields
```

### Required Database Update
```sql
UPDATE agents SET invoke_endpoint = 'http://localhost:8001/invoke' 
WHERE agent_id = 'agent:demo:pdf_summarizer:1.0.0';

UPDATE agents SET invoke_endpoint = 'http://localhost:8002/invoke' 
WHERE agent_id = 'agent:demo:translator:1.0.0';

UPDATE agents SET invoke_endpoint = 'http://localhost:8003/invoke' 
WHERE agent_id = 'agent:demo:scheduler:1.0.0';

UPDATE agents SET invoke_endpoint = 'http://localhost:8004/invoke' 
WHERE agent_id = 'agent:demo:weather:1.0.0';
```

## Testing Steps

### 1. Verify Mock Agents
```bash
curl http://localhost:8001/health
curl http://localhost:8002/health  
curl http://localhost:8003/health
curl http://localhost:8004/health
```

### 2. Test Agent Invocation
```bash
curl -X POST "http://localhost:8000/broker/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "agent_id": "agent:demo:translator:1.0.0",
    "capability_id": "translate_text", 
    "input": {"text": "Hello", "target_lang": "es"}
  }'
```

### 3. Test Demo Workflow
- Open http://localhost:8000/static/index.html
- Login with demo@aaww.io / demo
- Go to "Demo Workflow" tab
- Click "Run Demo Workflow"

## Files Modified

1. `src/static/index.html` - Fixed demo workflow field names
2. `src/schemas/registry.py` - Added invoke_endpoint to AgentListResponse
3. `src/simulators/mock_agents.py` - Fixed async/threading issues

## Next Steps

1. Create CLI tool for agent management
2. Update database with correct invoke endpoints
3. Test all agent invocations
4. Verify demo workflow works end-to-end

## Priority

**HIGH** - This blocks the demo workflow functionality completely. The 422 errors prevent users from testing the agent system.
