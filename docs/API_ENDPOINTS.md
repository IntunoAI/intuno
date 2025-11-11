# Intuno API Endpoints

## Authentication

### POST /auth/register
Register a new user
- **Body**: `UserRegister` (email, password, first_name?, last_name?)
- **Response**: `UserResponse`

### POST /auth/login
Login and get access token
- **Body**: `UserLogin` (email, password)
- **Response**: `TokenResponse` (access_token, token_type, expires_in)

### POST /auth/api-keys
Create a new API key (requires authentication)
- **Body**: `ApiKeyCreate` (name, expires_at?)
- **Response**: `ApiKeyResponse` (includes the actual key)

### GET /auth/api-keys
List user's API keys (requires authentication)
- **Response**: `List[ApiKeyListResponse]`

### DELETE /auth/api-keys/{key_id}
Delete an API key (requires authentication)
- **Response**: 204 No Content

### GET /auth/me
Get current user information (requires authentication)
- **Response**: `UserResponse`

## Registry

### POST /registry/agents
Register a new agent (requires authentication)
- **Body**: `AgentCreate` (manifest)
- **Response**: `AgentResponse`

### GET /registry/agents
List and search agents
- **Query params**: 
  - `tags`: List[str] - filter by tags
  - `capability`: str - filter by capability
  - `search`: str - text search
  - `limit`: int (1-100, default 20)
  - `offset`: int (default 0)
- **Response**: `List[AgentListResponse]`

### GET /registry/agents/{agent_id}
Get agent details by agent_id
- **Response**: `AgentResponse`

### PUT /registry/agents/{agent_uuid}
Update an agent (owner only, requires authentication)
- **Body**: `AgentUpdate` (manifest)
- **Response**: `AgentResponse`

### DELETE /registry/agents/{agent_uuid}
Delete an agent (owner only, requires authentication)
- **Response**: 204 No Content

### GET /registry/discover
Semantic discovery of agents
- **Query params**:
  - `query`: str - natural language query
  - `limit`: int (1-50, default 10)
- **Response**: `List[AgentListResponse]`

### GET /registry/my-agents
Get current user's agents (requires authentication)
- **Response**: `List[AgentListResponse]`

## Broker

### POST /broker/invoke
Invoke an agent capability through the broker (requires authentication)
- **Body**: `InvokeRequest` (agent_id, capability_id, input)
- **Response**: `InvokeResponse` (success, data?, error?, latency_ms, status_code)

### GET /broker/logs
Get invocation logs for the current user (requires authentication)
- **Query params**: `limit`: int (1-100, default 50)
- **Response**: `List[InvocationLogResponse]`

### GET /broker/logs/agent/{agent_id}
Get invocation logs for a specific agent (requires authentication)
- **Query params**: `limit`: int (1-100, default 50)
- **Response**: `List[InvocationLogResponse]`

## Health

### GET /health
Health check endpoint
- **Response**: `{"status": "healthy"}`

## Authentication Methods

The API supports two authentication methods:

1. **JWT Token**: Include `Authorization: Bearer <token>` header
2. **API Key**: Include `X-API-Key: <key>` header (to be implemented)

## Agent Manifest Format

Agents must provide a manifest following the Intuno specification:

```json
{
  "agent_id": "agent:namespace:name:version",
  "name": "Agent Name",
  "description": "Agent description",
  "version": "1.0.0",
  "endpoints": {
    "invoke": "https://example.com/invoke"
  },
  "capabilities": [{
    "id": "capability_name",
    "input_schema": {"type": "object", "properties": {...}},
    "output_schema": {"type": "object", "properties": {...}},
    "auth": {"type": "public"}
  }],
  "requires": [{"capability": "required_capability"}],
  "tags": ["tag1", "tag2"],
  "trust": {"verification": "self-signed"}
}
```
