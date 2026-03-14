---
description: Investigation summary - broker-to-agent auth gap and manifest auth_type not enforced
globs: src/services/broker.py, src/schemas/registry.py, src/models/registry.py
alwaysApply: false
---

# Broker-to-Agent Auth Gap (Investigation Summary)

## Problem

The broker calls agent invoke endpoints but has no per-agent auth mechanism. There is a gap between what the manifest declares and what the broker actually does.

## Current State

### What the manifest declares
- `capabilities[].auth_type`: `{"type": "public"|"api_key"|"bearer_token", "header"?: "...", "scheme"?: "..."}`. Header and scheme are configurable; defaults: api_key→X-API-Key, bearer_token→Authorization + Bearer. Persisted as JSON in `capabilities.auth_type`.
- `endpoints.invoke`: raw URL stored in `agents.invoke_endpoint`
- `manifest_json`: the full manifest is stored as JSONB in the agents table

### What the broker does (src/services/broker.py)
- POSTs to `agent.invoke_endpoint` with `Content-Type` and `User-Agent` headers
- Reads `capability.auth_type` and attaches credentials per-agent only
- Uses per-agent credentials from `agent_credentials` table (set via `POST /registry/agents/{uuid}/credentials`)
- No global API key; each agent must have its credential configured if `auth_type` is `api_key` or `bearer_token`

### What agent servers expect
- Chat/invoke endpoints typically validate `X-API-Key` header; the key must match the credential configured for that agent

## Resolved

1. **`auth_type` enforced** — broker reads `capability.auth_type` and sends `X-API-Key` when `api_key` or `bearer_token`; returns 503 if no per-agent credential is set.
2. **Per-agent credentials** — stored in `agent_credentials` table via `POST /registry/agents/{uuid}/credentials`.
3. **Manifest endpoints require auth** — agent detail no longer public.
4. **auth_type validation** — manifest validates enum: `public`, `api_key`, `bearer_token` (oauth2 deferred).
5. **SSRF protection** — invoke_endpoint validated (private IPs blocked, optional allowlist).

### Configurable auth header (credential or manifest)

Header/scheme live on the credential (set via `POST /registry/agents/{uuid}/credentials` with `auth_header`, `auth_scheme`). If not set, broker falls back to manifest `auth_type.header`/`auth_type.scheme`, then defaults (api_key→X-API-Key, bearer_token→Authorization+Bearer).

```json
// When setting credential
POST /registry/agents/{uuid}/credentials
{
  "credential_type": "api_key",
  "value": "secret-key",
  "auth_header": "X-Auth-Token",
  "auth_scheme": ""
}
```

Manifest `auth_type` can still specify header/scheme as fallback when credential doesn't have them.

## Future Work

- OAuth2 support when agent servers support it
