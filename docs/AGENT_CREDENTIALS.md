# Agent Credentials (Broker-to-Agent Auth)

When the broker invokes an agent, it sends the agent's credential (API key or bearer token) in the request. You configure this per agent via `POST /registry/agents/{uuid}/credentials`.

## API key with default header (X-API-Key)

Most agents expect the key in the `X-API-Key` header:

```bash
curl -X POST "http://localhost:8000/registry/agents/{agent_uuid}/credentials" \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"credential_type": "api_key", "value": "your-secret-key"}'
```

## Custom header name (e.g. X-Auth-Token)

If your agent server uses a different header:

```bash
curl -X POST "http://localhost:8000/registry/agents/{agent_uuid}/credentials" \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_type": "api_key",
    "value": "your-secret-key",
    "auth_header": "X-Auth-Token"
  }'
```

## Bearer token (Authorization header)

For OAuth2/JWT-style auth:

```bash
curl -X POST "http://localhost:8000/registry/agents/{agent_uuid}/credentials" \
  -H "Authorization: Bearer <your-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "credential_type": "bearer_token",
    "value": "eyJhbGciOiJIUzI1NiIs...",
    "auth_header": "Authorization",
    "auth_scheme": "Bearer"
  }'
```

This sends `Authorization: Bearer eyJhbGciOiJIUzI1NiIs...` to the agent.

## Bulk inject (scripts)

For local development, use the inject script to set credentials for all agents:

```bash
export AGENTS_API_KEY=your-shared-dev-key
python scripts/inject_agent_credentials.py

# With custom header
python scripts/inject_agent_credentials.py --api-key "key" --header "X-Auth-Token"
```
