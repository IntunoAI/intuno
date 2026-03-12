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
- `capabilities[].auth_type`: stored as `{"type": "public"}` in the manifest, persisted as a plain string (`"public"`) in `capabilities.auth_type` column
- `endpoints.invoke`: raw URL stored in `agents.invoke_endpoint`
- `manifest_json`: the full manifest is stored as JSONB in the agents table

### What the broker does (src/services/broker.py)
- POSTs to `agent.invoke_endpoint` with `Content-Type` and `User-Agent` headers
- Since the recent fix: also sends a **global** `AGENTS_API_KEY` via `X-API-Key` header (from settings)
- Does **NOT** read or act on `capability.auth_type` at all
- Does **NOT** support per-agent credentials

### What wisdom-agents expects (agents/core/auth.py)
- All chat endpoints require `X-API-Key` matching `AGENTS_API_KEY` env var
- Single shared secret for all agents on that server

## Identified Gaps

1. **`auth_type` is decorative** — the capability `auth_type` field is stored but never checked or used by the broker. An agent declaring `auth_type: "oauth2"` would be invoked identically to `auth_type: "public"`.

2. **No per-agent auth** — the `AGENTS_API_KEY` is a single global key. If agents are hosted across different servers with different credentials, there is no way to configure per-agent API keys, OAuth tokens, or other auth mechanisms.

3. **`manifest_json` exposed publicly** — `GET /registry/agents/{agent_id}` (public, no auth) returns `manifest_json` which is the full raw manifest. If an agent owner puts sensitive data (API keys, internal URLs) in the manifest, it gets exposed. Currently manifests don't have an auth_credentials field, but the raw JSONB could contain anything.

4. **No auth_type validation** — the manifest accepts any string for `auth_type` without validation (e.g., `"public"`, `"api_key"`, `"oauth2"`), but the broker treats them all the same.

5. **Invoke endpoint not validated** — the broker calls whatever URL is in `invoke_endpoint` without any allowlist, SSRF protection, or domain restriction.

## Suggested Future Work

- Define a proper `auth_type` enum: `public`, `api_key`, `oauth2`, `bearer_token`
- Add per-agent auth config (e.g., an `agent_credentials` table or encrypted field)
- Make the broker read `auth_type` and attach the right credential when invoking
- Sanitize/redact `manifest_json` before returning it on public endpoints
- Add SSRF protection for invoke_endpoint (allowlist, private IP blocking)
