"""
End-to-end workflow test script for the Wisdom backend.

Prerequisites:
  1. Wisdom backend running on BASE_URL (default http://localhost:8000)
  2. Calculator demo agent running on port 8001
     (cd demo && python -m uvicorn agents.calculator_agent:app --port 8001)
  3. PostgreSQL + Qdrant accessible per .env

Usage:
  cd wisdom
  python -m tests.test_workflow            # run all
  python -m tests.test_workflow --base-url http://localhost:8000
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from typing import Any, Dict, Optional

import httpx

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"


class WorkflowTestRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30)
        self.results: list[tuple[str, bool, str]] = []

        self.jwt_token: Optional[str] = None
        self.user_id: Optional[str] = None
        self.personal_api_key: Optional[str] = None
        self.integration_id: Optional[str] = None
        self.integration_api_key: Optional[str] = None
        self.agent_uuid: Optional[str] = None
        self.agent_id_str: Optional[str] = None

    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = PASS if passed else FAIL
        print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((name, passed, detail))

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.jwt_token}"}

    def _api_key_headers(self, key: str) -> Dict[str, str]:
        return {"X-API-Key": key}

    # ── 1. Health ──────────────────────────────────────────────────────

    async def test_health(self):
        r = await self.client.get("/health")
        self._record("GET /health", r.status_code == 200, f"status={r.status_code}")

    # ── 2. Auth ────────────────────────────────────────────────────────

    async def test_register(self):
        suffix = uuid.uuid4().hex[:8]
        payload = {
            "email": f"test-{suffix}@intuno.dev",
            "password": "TestPass123!",
            "first_name": "Test",
            "last_name": "User",
        }
        r = await self.client.post("/auth/register", json=payload)
        ok = r.status_code in (200, 201)
        if ok:
            data = r.json()
            self.user_id = str(data.get("id", ""))
        self._record("POST /auth/register", ok, f"status={r.status_code}")
        return payload["email"], payload["password"]

    async def test_login(self, email: str, password: str):
        r = await self.client.post("/auth/login", json={"email": email, "password": password})
        ok = r.status_code == 200
        if ok:
            data = r.json()
            self.jwt_token = data.get("access_token")
        self._record("POST /auth/login", ok, f"status={r.status_code}")

    async def test_me(self):
        r = await self.client.get("/auth/me", headers=self._auth_headers())
        ok = r.status_code == 200 and r.json().get("email") is not None
        self._record("GET /auth/me", ok, f"status={r.status_code}")

    async def test_create_personal_api_key(self):
        r = await self.client.post(
            "/auth/api-keys",
            json={"name": "test-personal-key"},
            headers=self._auth_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.personal_api_key = r.json().get("key")
        self._record("POST /auth/api-keys (personal)", ok, f"status={r.status_code}")

    async def test_list_api_keys(self):
        r = await self.client.get("/auth/api-keys", headers=self._auth_headers())
        ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1
        self._record("GET /auth/api-keys", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    # ── 3. Integrations (apps) ─────────────────────────────────────────

    async def test_create_integration(self):
        r = await self.client.post(
            "/integrations",
            json={"name": "Test Chat App", "kind": "chat"},
            headers=self._auth_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.integration_id = str(r.json()["id"])
        self._record("POST /integrations", ok, f"status={r.status_code}")

    async def test_create_integration_api_key(self):
        r = await self.client.post(
            f"/integrations/{self.integration_id}/api-keys",
            json={"name": "test-integration-key"},
            headers=self._auth_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.integration_api_key = r.json().get("key")
        self._record("POST /integrations/{id}/api-keys", ok, f"status={r.status_code}")

    async def test_list_integrations(self):
        r = await self.client.get("/integrations", headers=self._auth_headers())
        ok = r.status_code == 200 and len(r.json()) >= 1
        self._record("GET /integrations", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    # ── 4. Registry ────────────────────────────────────────────────────

    async def test_register_agent(self):
        manifest = {
            "agent_id": f"agent:test:calc:{uuid.uuid4().hex[:6]}",
            "name": "Test Calculator",
            "description": "A calculator for testing",
            "version": "1.0.0",
            "endpoints": {"invoke": "http://localhost:8001/invoke"},
            "capabilities": [
                {
                    "id": "add",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {"result": {"type": "number"}},
                    },
                    "auth_type": {"type": "public"},
                },
                {
                    "id": "multiply",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "a": {"type": "number"},
                            "b": {"type": "number"},
                        },
                        "required": ["a", "b"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {"result": {"type": "number"}},
                    },
                    "auth_type": {"type": "public"},
                },
            ],
            "tags": ["math", "test"],
            "trust": {"verification": "self-signed"},
        }
        r = await self.client.post(
            "/registry/agents?enhance_manifest=false",
            json={"manifest": manifest},
            headers=self._auth_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            data = r.json()
            self.agent_uuid = str(data["id"])
            self.agent_id_str = data["agent_id"]
        self._record(
            "POST /registry/agents",
            ok,
            f"status={r.status_code}" + (f" agent_id={self.agent_id_str}" if ok else f" body={r.text[:200]}"),
        )

    async def test_list_agents(self):
        r = await self.client.get("/registry/agents", headers=self._auth_headers())
        ok = r.status_code == 200 and len(r.json()) >= 1
        self._record("GET /registry/agents", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_get_agent_public(self):
        r = await self.client.get(f"/registry/agents/{self.agent_id_str}")
        ok = r.status_code == 200 and r.json()["agent_id"] == self.agent_id_str
        self._record("GET /registry/agents/{agent_id} (public)", ok, f"status={r.status_code}")

    async def test_my_agents(self):
        r = await self.client.get("/registry/my-agents", headers=self._auth_headers())
        ok = r.status_code == 200 and any(a["id"] == self.agent_uuid for a in r.json())
        self._record("GET /registry/my-agents", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_discover(self):
        r = await self.client.get(
            "/registry/discover",
            params={"query": "calculator math add numbers", "limit": 5, "enhance_query": "false"},
        )
        ok = r.status_code == 200
        agents = r.json() if ok else []
        found = any(a.get("agent_id") == self.agent_id_str for a in agents)
        self._record("GET /registry/discover", ok, f"count={len(agents)}, found_ours={found}")

    # ── 5. Broker invoke (single-user, personal key) ──────────────────

    async def test_broker_invoke_personal(self):
        """Invoke via personal API key — single-user app pattern."""
        if not self.personal_api_key:
            self._record("POST /broker/invoke (personal key)", False, "no key")
            return
        r = await self.client.post(
            "/broker/invoke",
            json={
                "agent_id": self.agent_id_str,
                "capability_id": "add",
                "input": {"a": 7, "b": 3},
            },
            headers=self._api_key_headers(self.personal_api_key),
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        success = data.get("success", False)
        result = data.get("data", {}).get("result") if success else None
        self._record(
            "POST /broker/invoke (personal key)",
            ok and success and result == 10,
            f"status={r.status_code} success={success} result={result}",
        )

    # ── 6. Broker invoke (multi-user, integration key + external_user_id)

    async def test_broker_invoke_multiuser(self):
        """Invoke via integration API key with external_user_id — multi-user app pattern."""
        if not self.integration_api_key:
            self._record("POST /broker/invoke (integration key)", False, "no key")
            return
        r = await self.client.post(
            "/broker/invoke",
            json={
                "agent_id": self.agent_id_str,
                "capability_id": "multiply",
                "input": {"a": 6, "b": 7},
                "external_user_id": "end-user-alice",
            },
            headers=self._api_key_headers(self.integration_api_key),
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        success = data.get("success", False)
        result = data.get("data", {}).get("result") if success else None
        conv_id = data.get("conversation_id")
        self._record(
            "POST /broker/invoke (integration key + external_user_id)",
            ok and success and result == 42,
            f"status={r.status_code} success={success} result={result} conv={conv_id}",
        )
        return conv_id

    # ── 7. Conversation scoping ────────────────────────────────────────

    async def test_conversations(self, expected_external_user: str = "end-user-alice"):
        r = await self.client.get(
            "/conversations",
            params={"external_user_id": expected_external_user},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        convs = r.json() if ok else []
        has_alice = any(c.get("external_user_id") == expected_external_user for c in convs)
        self._record(
            "GET /conversations?external_user_id=end-user-alice",
            ok and has_alice,
            f"count={len(convs)} has_alice={has_alice}",
        )

    # ── 8. Invocation logs (scoped) ───────────────────────────────────

    async def test_invocation_logs(self):
        r = await self.client.get("/broker/logs", headers=self._auth_headers())
        ok = r.status_code == 200 and len(r.json()) >= 1
        self._record("GET /broker/logs", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_invocation_logs_by_agent(self):
        r = await self.client.get(
            f"/broker/logs/agent/{self.agent_uuid}",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and len(r.json()) >= 1
        self._record(
            "GET /broker/logs/agent/{id}",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    # ── 9. Ratings ─────────────────────────────────────────────────────

    async def test_rate_agent(self):
        r = await self.client.post(
            f"/registry/agents/{self.agent_id_str}/rate",
            json={"score": 5, "comment": "Great test agent!"},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        self._record("POST /registry/agents/{id}/rate", ok, f"status={r.status_code}")

    async def test_list_ratings(self):
        r = await self.client.get(f"/registry/agents/{self.agent_id_str}/ratings")
        ok = r.status_code == 200 and len(r.json()) >= 1
        self._record("GET /registry/agents/{id}/ratings (public)", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    # ── 10. Cleanup ────────────────────────────────────────────────────

    async def test_delete_agent(self):
        r = await self.client.delete(
            f"/registry/agents/{self.agent_uuid}",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 204
        self._record("DELETE /registry/agents/{uuid}", ok, f"status={r.status_code}")

    # ── Runner ─────────────────────────────────────────────────────────

    async def run_all(self):
        print(f"\n{'='*60}")
        print(f"  Wisdom Backend Workflow Tests")
        print(f"  Target: {self.base_url}")
        print(f"{'='*60}\n")

        print("── Health ──")
        await self.test_health()

        print("\n── Auth ──")
        email, pw = await self.test_register()
        await self.test_login(email, pw)
        await self.test_me()
        await self.test_create_personal_api_key()
        await self.test_list_api_keys()

        print("\n── Integrations ──")
        await self.test_create_integration()
        await self.test_create_integration_api_key()
        await self.test_list_integrations()

        print("\n── Registry ──")
        await self.test_register_agent()
        await self.test_list_agents()
        await self.test_get_agent_public()
        await self.test_my_agents()
        await self.test_discover()

        print("\n── Broker (single-user) ──")
        await self.test_broker_invoke_personal()

        print("\n── Broker (multi-user) ──")
        await self.test_broker_invoke_multiuser()

        print("\n── Conversations ──")
        await self.test_conversations()

        print("\n── Invocation Logs ──")
        await self.test_invocation_logs()
        await self.test_invocation_logs_by_agent()

        print("\n── Ratings ──")
        await self.test_rate_agent()
        await self.test_list_ratings()

        print("\n── Cleanup ──")
        await self.test_delete_agent()

        await self.client.aclose()
        self._print_summary()

    def _print_summary(self):
        total = len(self.results)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = total - passed
        print(f"\n{'='*60}")
        print(f"  Results: {passed}/{total} passed, {failed} failed")
        if failed:
            print(f"\n  Failed tests:")
            for name, ok, detail in self.results:
                if not ok:
                    print(f"    - {name}: {detail}")
        print(f"{'='*60}\n")
        if failed:
            sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="Wisdom backend workflow tests")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()

    runner = WorkflowTestRunner(args.base_url)
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
