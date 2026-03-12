"""
End-to-end workflow test script for the Wisdom backend.

Assumes agents are already registered on the server — skips agent
registration/deletion and any other destructive actions.

Prerequisites:
  1. Wisdom backend running on BASE_URL (default http://localhost:8000)
  2. At least one agent already registered in the registry
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
import uuid
from typing import Any, Dict, List, Optional

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
        self.first_capability_id: Optional[str] = None
        self.first_capability_input_schema: Optional[Dict[str, Any]] = None

    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = PASS if passed else FAIL
        print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((name, passed, detail))

    def _skip(self, name: str, reason: str = ""):
        print(f"  [{SKIP}] {name}" + (f"  ({reason})" if reason else ""))

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

    async def test_get_integration(self):
        if not self.integration_id:
            self._skip("GET /integrations/{id}", "no integration_id")
            return
        r = await self.client.get(
            f"/integrations/{self.integration_id}",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        self._record("GET /integrations/{id}", ok, f"status={r.status_code}")

    async def test_list_integration_api_keys(self):
        if not self.integration_id:
            self._skip("GET /integrations/{id}/api-keys", "no integration_id")
            return
        r = await self.client.get(
            f"/integrations/{self.integration_id}/api-keys",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /integrations/{id}/api-keys",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    # ── 4. Registry (read-only — agents already on server) ─────────────

    @staticmethod
    def _build_sample_input(input_schema: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Build a minimal sample input dict from a JSON Schema."""
        if not input_schema or input_schema.get("type") != "object":
            return {}
        props = input_schema.get("properties", {})
        sample: Dict[str, Any] = {}
        for key, spec in props.items():
            t = spec.get("type", "string")
            if t == "number" or t == "integer":
                sample[key] = 1
            elif t == "boolean":
                sample[key] = True
            elif t == "array":
                sample[key] = []
            elif t == "object":
                sample[key] = {}
            else:
                sample[key] = "test"
        return sample

    async def test_fetch_existing_agent(self):
        """Fetch an existing agent from the registry to use in subsequent tests."""
        r = await self.client.get(
            "/registry/agents",
            params={"limit": 10},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        agents = r.json() if ok else []
        if agents:
            first = agents[0]
            self.agent_uuid = str(first["id"])
            self.agent_id_str = first["agent_id"]
            caps = first.get("capabilities", [])
            if caps:
                cap = caps[0]
                self.first_capability_id = cap.get("id") or cap.get("capability_id")
                self.first_capability_input_schema = cap.get("input_schema")
        self._record(
            "GET /registry/agents (fetch existing)",
            ok and len(agents) >= 1,
            f"count={len(agents)}"
            + (f" using agent_id={self.agent_id_str} cap={self.first_capability_id}" if self.agent_id_str else " NO AGENTS FOUND"),
        )

    async def test_list_agents(self):
        r = await self.client.get("/registry/agents", headers=self._auth_headers())
        ok = r.status_code == 200 and len(r.json()) >= 1
        self._record("GET /registry/agents", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_get_agent(self):
        if not self.agent_id_str:
            self._skip("GET /registry/agents/{agent_id}", "no agent")
            return
        r = await self.client.get(
            f"/registry/agents/{self.agent_id_str}",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and r.json()["agent_id"] == self.agent_id_str
        self._record("GET /registry/agents/{agent_id}", ok, f"status={r.status_code}")

    async def test_my_agents(self):
        r = await self.client.get("/registry/my-agents", headers=self._auth_headers())
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record("GET /registry/my-agents", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_new_agents(self):
        r = await self.client.get(
            "/registry/agents/new",
            params={"days": 30, "limit": 10},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record("GET /registry/agents/new", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_trending_agents(self):
        r = await self.client.get(
            "/registry/agents/trending",
            params={"window_days": 30, "limit": 10},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record("GET /registry/agents/trending", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_discover(self):
        r = await self.client.get(
            "/registry/discover",
            params={"query": "calculator math add numbers", "limit": 5, "enhance_query": "false"},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        agents = r.json() if ok else []
        found = any(a.get("agent_id") == self.agent_id_str for a in agents) if self.agent_id_str else False
        self._record("GET /registry/discover", ok, f"count={len(agents)}, found_ours={found}")

    # ── 5. Ratings (read + write, non-destructive) ─────────────────────

    async def test_rate_agent(self):
        if not self.agent_id_str:
            self._skip("POST /registry/agents/{id}/rate", "no agent")
            return
        r = await self.client.post(
            f"/registry/agents/{self.agent_id_str}/rate",
            json={"score": 5, "comment": "Great test agent!"},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        self._record("POST /registry/agents/{id}/rate", ok, f"status={r.status_code}")

    async def test_list_ratings(self):
        if not self.agent_id_str:
            self._skip("GET /registry/agents/{id}/ratings", "no agent")
            return
        r = await self.client.get(
            f"/registry/agents/{self.agent_id_str}/ratings",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /registry/agents/{id}/ratings",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    # ── 6. Broker invoke (single-user, personal key) ──────────────────

    async def test_broker_invoke_personal(self):
        if not self.personal_api_key or not self.agent_id_str or not self.first_capability_id:
            self._skip(
                "POST /broker/invoke (personal key)",
                f"key={bool(self.personal_api_key)} agent={bool(self.agent_id_str)} cap={bool(self.first_capability_id)}",
            )
            return
        test_input = self._build_sample_input(self.first_capability_input_schema)
        r = await self.client.post(
            "/broker/invoke",
            json={
                "agent_id": self.agent_id_str,
                "capability_id": self.first_capability_id,
                "input": test_input,
            },
            headers=self._api_key_headers(self.personal_api_key),
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        success = data.get("success", False)
        error = data.get("error")
        self._record(
            "POST /broker/invoke (personal key)",
            ok and success,
            f"status={r.status_code} success={success} data={data.get('data')}"
            + (f" error={error}" if error else ""),
        )

    # ── 7. Broker invoke (multi-user, integration key + external_user_id)

    async def test_broker_invoke_multiuser(self) -> Optional[str]:
        if not self.integration_api_key or not self.agent_id_str or not self.first_capability_id:
            self._skip(
                "POST /broker/invoke (integration key)",
                f"key={bool(self.integration_api_key)} agent={bool(self.agent_id_str)} cap={bool(self.first_capability_id)}",
            )
            return None
        test_input = self._build_sample_input(self.first_capability_input_schema)
        r = await self.client.post(
            "/broker/invoke",
            json={
                "agent_id": self.agent_id_str,
                "capability_id": self.first_capability_id,
                "input": test_input,
                "external_user_id": "end-user-alice",
            },
            headers=self._api_key_headers(self.integration_api_key),
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        success = data.get("success", False)
        conv_id = data.get("conversation_id")
        error = data.get("error")
        self._record(
            "POST /broker/invoke (integration key + external_user_id)",
            ok and success,
            f"status={r.status_code} success={success} data={data.get('data')} conv={conv_id}"
            + (f" error={error}" if error else ""),
        )
        return conv_id

    # ── 8. Conversations (read-only) ──────────────────────────────────

    async def test_list_conversations(self):
        r = await self.client.get("/conversations", headers=self._auth_headers())
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /conversations",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    async def test_list_conversations_filtered(self, expected_external_user: str = "end-user-alice"):
        r = await self.client.get(
            "/conversations",
            params={"external_user_id": expected_external_user},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        convs = r.json() if ok else []
        has_alice = any(c.get("external_user_id") == expected_external_user for c in convs)
        self._record(
            f"GET /conversations?external_user_id={expected_external_user}",
            ok and has_alice,
            f"count={len(convs)} has_user={has_alice}",
        )

    async def test_get_conversation(self, conversation_id: Optional[str]):
        if not conversation_id:
            self._skip("GET /conversations/{id}", "no conversation_id")
            return
        r = await self.client.get(
            f"/conversations/{conversation_id}",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        self._record("GET /conversations/{id}", ok, f"status={r.status_code}")

    async def test_conversation_logs(self, conversation_id: Optional[str]):
        if not conversation_id:
            self._skip("GET /conversations/{id}/logs", "no conversation_id")
            return
        r = await self.client.get(
            f"/conversations/{conversation_id}/logs",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /conversations/{id}/logs",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    async def test_conversation_messages(self, conversation_id: Optional[str]):
        if not conversation_id:
            self._skip("GET /conversations/{id}/messages", "no conversation_id")
            return
        r = await self.client.get(
            f"/conversations/{conversation_id}/messages",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /conversations/{id}/messages",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    # ── 9. Invocation logs ────────────────────────────────────────────

    async def test_invocation_logs(self):
        r = await self.client.get("/broker/logs", headers=self._auth_headers())
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record("GET /broker/logs", ok, f"count={len(r.json()) if r.status_code == 200 else 'N/A'}")

    async def test_invocation_logs_by_agent(self):
        if not self.agent_uuid:
            self._skip("GET /broker/logs/agent/{id}", "no agent_uuid")
            return
        r = await self.client.get(
            f"/broker/logs/agent/{self.agent_uuid}",
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /broker/logs/agent/{id}",
            ok,
            f"count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    # ── 10. Tasks ─────────────────────────────────────────────────────

    async def test_create_task_sync(self):
        if not self.personal_api_key:
            self._skip("POST /tasks (sync)", "no api key")
            return
        test_input = self._build_sample_input(self.first_capability_input_schema)
        r = await self.client.post(
            "/tasks",
            json={"goal": "Perform a simple calculation", "input": test_input},
            headers=self._api_key_headers(self.personal_api_key),
        )
        ok = r.status_code in (200, 201)
        data = r.json() if ok else {}
        task_id = data.get("id") or data.get("task_id")
        error = data.get("error_message") or data.get("error")
        self._record(
            "POST /tasks (sync)",
            ok,
            f"status={r.status_code} task_id={task_id} result={data.get('result', 'N/A')}"
            + (f" error={error}" if error else ""),
        )
        return task_id

    async def test_create_task_async(self):
        if not self.personal_api_key:
            self._skip("POST /tasks (async)", "no api key")
            return None
        test_input = self._build_sample_input(self.first_capability_input_schema)
        r = await self.client.post(
            "/tasks",
            params={"async": "true"},
            json={"goal": "Perform a simple calculation async", "input": test_input},
            headers=self._api_key_headers(self.personal_api_key),
        )
        ok = r.status_code == 202
        data = r.json() if ok else {}
        task_id = data.get("task_id")
        self._record(
            "POST /tasks (async)",
            ok,
            f"status={r.status_code} task_id={task_id}",
        )
        return task_id

    async def test_get_task(self, task_id: Optional[str]):
        if not task_id or not self.personal_api_key:
            self._skip("GET /tasks/{id}", "no task_id or api key")
            return
        r = await self.client.get(
            f"/tasks/{task_id}",
            headers=self._api_key_headers(self.personal_api_key),
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        error = data.get("error_message") or data.get("error")
        self._record(
            "GET /tasks/{id}",
            ok,
            f"status={r.status_code} task_status={data.get('status', 'N/A')}"
            + (f" error={error}" if error else ""),
        )

    async def test_poll_task(self, task_id: Optional[str]):
        if not task_id or not self.personal_api_key:
            self._skip("GET /tasks/{id} (poll)", "no task_id or api key")
            return
        for attempt in range(10):
            await asyncio.sleep(1)
            r = await self.client.get(
                f"/tasks/{task_id}",
                headers=self._api_key_headers(self.personal_api_key),
            )
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get("status") in ("completed", "failed", "timeout"):
                error = data.get("error_message") or data.get("error")
                self._record(
                    "GET /tasks/{id} (poll)",
                    data["status"] == "completed",
                    f"attempts={attempt + 1} status={data['status']} result={data.get('result', 'N/A')}"
                    + (f" error={error}" if error else ""),
                )
                return
        self._record("GET /tasks/{id} (poll)", False, "timed out after 10 attempts")

    # ── Runner ─────────────────────────────────────────────────────────

    async def run_all(self):
        print(f"\n{'='*60}")
        print(f"  Wisdom Backend Workflow Tests")
        print(f"  Target: {self.base_url}")
        print(f"  (agent registration & destructive actions skipped)")
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
        await self.test_get_integration()
        await self.test_list_integration_api_keys()

        print("\n── Registry (existing agents) ──")
        await self.test_fetch_existing_agent()
        await self.test_list_agents()
        await self.test_get_agent()
        await self.test_my_agents()
        await self.test_new_agents()
        await self.test_trending_agents()
        await self.test_discover()

        print("\n── Ratings ──")
        await self.test_rate_agent()
        await self.test_list_ratings()

        print("\n── Broker (single-user) ──")
        await self.test_broker_invoke_personal()

        print("\n── Broker (multi-user) ──")
        conv_id = await self.test_broker_invoke_multiuser()

        print("\n── Conversations ──")
        await self.test_list_conversations()
        await self.test_list_conversations_filtered()
        await self.test_get_conversation(conv_id)
        await self.test_conversation_logs(conv_id)
        await self.test_conversation_messages(conv_id)

        print("\n── Invocation Logs ──")
        await self.test_invocation_logs()
        await self.test_invocation_logs_by_agent()

        print("\n── Tasks ──")
        sync_task_id = await self.test_create_task_sync()
        await self.test_get_task(sync_task_id)
        async_task_id = await self.test_create_task_async()
        await self.test_poll_task(async_task_id)

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
