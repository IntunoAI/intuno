"""
End-to-end tests for the new workflow orchestrator (DAG-based).

Tests the /workflows and /executions routes introduced in wisdom/src/workflow/.

Prerequisites:
  1. Wisdom backend running on BASE_URL (default http://localhost:8000)
  2. At least one agent already registered in the registry
  3. PostgreSQL + Redis accessible per .env

Usage:
  cd wisdom
  python -m tests.test_new_orchestrator
  python -m tests.test_new_orchestrator --base-url http://localhost:8000
"""

import argparse
import asyncio
import sys
import uuid
from typing import Any, Dict, Optional

import httpx

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

POLL_MAX_SECONDS = 30
POLL_INTERVAL_SECONDS = 1


class NewOrchestratorTestRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60)
        self.results: list[tuple[str, bool, str]] = []

        self.jwt_token: Optional[str] = None
        self.api_key: Optional[str] = None

        # IDs persisted across tests
        self.workflow_id: Optional[str] = None
        self.parallel_workflow_id: Optional[str] = None
        self.conditional_workflow_id: Optional[str] = None
        self.child_workflow_id: Optional[str] = None
        self.parent_workflow_id: Optional[str] = None
        self.execution_id: Optional[str] = None
        self.running_execution_id: Optional[str] = None

        # Agent from registry to use in step definitions
        self.agent_ref: Optional[str] = None

    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = PASS if passed else FAIL
        print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((name, passed, detail))

    def _skip(self, name: str, reason: str = ""):
        print(f"  [{SKIP}] {name}" + (f"  ({reason})" if reason else ""))

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.jwt_token}"}

    def _api_key_headers(self) -> Dict[str, str]:
        return {"X-API-Key": self.api_key}

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    async def _bootstrap(self):
        """Register a user, log in, create an API key, and find an agent to use."""
        suffix = uuid.uuid4().hex[:8]
        email = f"wf-test-{suffix}@intuno.dev"
        password = "TestPass123!"

        r = await self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "first_name": "WF", "last_name": "Test"},
        )
        if r.status_code not in (200, 201):
            print(f"  Bootstrap failed: register returned {r.status_code}")
            sys.exit(1)

        r = await self.client.post("/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"  Bootstrap failed: login returned {r.status_code}")
            sys.exit(1)
        self.jwt_token = r.json()["access_token"]

        r = await self.client.post(
            "/auth/api-keys",
            json={"name": "wf-test-key"},
            headers=self._auth_headers(),
        )
        if r.status_code not in (200, 201):
            print(f"  Bootstrap failed: api-key creation returned {r.status_code}")
            sys.exit(1)
        self.api_key = r.json()["key"]

        # Find an agent to use in workflow steps
        r = await self.client.get(
            "/registry/agents",
            params={"limit": 1},
            headers=self._api_key_headers(),
        )
        if r.status_code == 200 and r.json():
            self.agent_ref = r.json()[0].get("agent_id")

    # ── Phase A: Basic workflow lifecycle ─────────────────────────────────────

    async def test_create_simple_workflow(self):
        """POST /workflows — single agent step."""
        definition: Dict[str, Any] = {
            "name": "simple-test",
            "steps": [],
        }
        if self.agent_ref:
            definition["steps"] = [
                {"id": "step1", "agent": self.agent_ref, "input": {"prompt": "hello"}}
            ]
        else:
            # Use a plan step so we don't need a real agent
            definition["steps"] = [
                {"id": "step1", "type": "plan", "goal": "say hello"}
            ]

        r = await self.client.post(
            "/workflows",
            json={"name": "simple-test", "definition": definition},
            headers=self._api_key_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.workflow_id = str(r.json()["id"])
        self._record(
            "POST /workflows (simple)",
            ok,
            f"status={r.status_code}" + (f" id={self.workflow_id}" if ok else f" body={r.text[:120]}"),
        )

    async def test_get_workflow(self):
        """GET /workflows/{id}."""
        if not self.workflow_id:
            self._skip("GET /workflows/{id}", "no workflow_id")
            return
        r = await self.client.get(
            f"/workflows/{self.workflow_id}",
            headers=self._api_key_headers(),
        )
        ok = r.status_code == 200 and str(r.json()["id"]) == self.workflow_id
        self._record("GET /workflows/{id}", ok, f"status={r.status_code}")

    async def test_list_workflows(self):
        """GET /workflows — list includes the one we just created."""
        r = await self.client.get("/workflows", headers=self._api_key_headers())
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /workflows",
            ok,
            f"status={r.status_code} count={len(r.json()) if ok else 'N/A'}",
        )

    async def test_trigger_execution(self):
        """POST /workflows/{id}/run — trigger an execution."""
        if not self.workflow_id:
            self._skip("POST /workflows/{id}/run", "no workflow_id")
            return
        r = await self.client.post(
            f"/workflows/{self.workflow_id}/run",
            json={"trigger_data": {"source": "test"}},
            headers=self._api_key_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.execution_id = str(r.json()["id"])
        self._record(
            "POST /workflows/{id}/run",
            ok,
            f"status={r.status_code}" + (f" exec_id={self.execution_id}" if ok else f" body={r.text[:120]}"),
        )

    async def test_get_execution_status(self):
        """GET /executions/{id} — poll until terminal or timeout."""
        if not self.execution_id:
            self._skip("GET /executions/{id}", "no execution_id")
            return

        final_status = None
        for _ in range(POLL_MAX_SECONDS):
            r = await self.client.get(
                f"/executions/{self.execution_id}",
                headers=self._api_key_headers(),
            )
            if r.status_code != 200:
                break
            status = r.json().get("status")
            if status in ("completed", "failed", "cancelled", "timed_out"):
                final_status = status
                break
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        ok = final_status is not None
        self._record(
            "GET /executions/{id} (poll to terminal)",
            ok,
            f"final_status={final_status}",
        )

    async def test_get_process_table(self):
        """GET /executions/{id}/ps — verify process entries exist."""
        if not self.execution_id:
            self._skip("GET /executions/{id}/ps", "no execution_id")
            return
        r = await self.client.get(
            f"/executions/{self.execution_id}/ps",
            headers=self._api_key_headers(),
        )
        ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1
        self._record(
            "GET /executions/{id}/ps",
            ok,
            f"status={r.status_code} entries={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    # ── Phase B: DAG features ─────────────────────────────────────────────────

    async def test_create_parallel_workflow(self):
        """POST /workflows — two steps with no dependency (run in parallel)."""
        if not self.agent_ref:
            self._skip("POST /workflows (parallel)", "no agent registered")
            return
        definition: Dict[str, Any] = {
            "name": "parallel-test",
            "steps": [
                {"id": "stepA", "agent": self.agent_ref, "input": {"prompt": "A"}},
                {"id": "stepB", "agent": self.agent_ref, "input": {"prompt": "B"}},
            ],
        }
        r = await self.client.post(
            "/workflows",
            json={"name": "parallel-test", "definition": definition},
            headers=self._api_key_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.parallel_workflow_id = str(r.json()["id"])
        self._record("POST /workflows (parallel steps)", ok, f"status={r.status_code}")

    async def test_create_conditional_workflow(self):
        """POST /workflows — condition step with when clause."""
        definition: Dict[str, Any] = {
            "name": "conditional-test",
            "steps": [
                {
                    "id": "check",
                    "type": "condition",
                    "when": [
                        {"if": "trigger.value > 0", "goto": "positive"},
                        {"else": True, "goto": "negative"},
                    ],
                },
                {"id": "positive", "type": "plan", "goal": "handle positive value"},
                {"id": "negative", "type": "plan", "goal": "handle negative value"},
            ],
        }
        r = await self.client.post(
            "/workflows",
            json={"name": "conditional-test", "definition": definition},
            headers=self._api_key_headers(),
        )
        ok = r.status_code in (200, 201)
        if ok:
            self.conditional_workflow_id = str(r.json()["id"])
        self._record("POST /workflows (conditional)", ok, f"status={r.status_code}")

    async def test_trigger_conditional_and_check_skipped(self):
        """Trigger conditional workflow with value > 0 and verify 'negative' step is skipped."""
        if not self.conditional_workflow_id:
            self._skip("conditional execution + skipped step check", "no conditional_workflow_id")
            return

        r = await self.client.post(
            f"/workflows/{self.conditional_workflow_id}/run",
            json={"trigger_data": {"value": 1}},
            headers=self._api_key_headers(),
        )
        if r.status_code not in (200, 201):
            self._record(
                "conditional: trigger returns 201",
                False,
                f"status={r.status_code} body={r.text[:120]}",
            )
            return

        exec_id = str(r.json()["id"])

        # Poll to terminal
        final_status = None
        for _ in range(POLL_MAX_SECONDS):
            r2 = await self.client.get(
                f"/executions/{exec_id}", headers=self._api_key_headers()
            )
            if r2.status_code == 200:
                s = r2.json().get("status")
                if s in ("completed", "failed", "cancelled", "timed_out"):
                    final_status = s
                    break
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        # Check process table for a skipped entry
        r3 = await self.client.get(
            f"/executions/{exec_id}/ps", headers=self._api_key_headers()
        )
        skipped_entries = []
        if r3.status_code == 200:
            skipped_entries = [e for e in r3.json() if e.get("status") == "skipped"]

        ok = final_status is not None and len(skipped_entries) >= 1
        self._record(
            "conditional: skipped step appears in process table",
            ok,
            f"final={final_status} skipped={len(skipped_entries)}",
        )

    # ── Phase C: Error handling & cancellation ────────────────────────────────

    async def test_create_workflow_bad_reference(self):
        """POST /workflows referencing a non-existent agent — workflow creation still succeeds
        (validation is at execution time, not creation time)."""
        definition: Dict[str, Any] = {
            "name": "bad-ref-test",
            "steps": [
                {"id": "step1", "agent": "agent:nonexistent:ghost:v1", "input": {}}
            ],
        }
        r = await self.client.post(
            "/workflows",
            json={"name": "bad-ref-test", "definition": definition},
            headers=self._api_key_headers(),
        )
        # Creation should succeed — validation is deferred to execution time
        ok = r.status_code in (200, 201)
        self._record(
            "POST /workflows (bad agent ref) — creation allowed",
            ok,
            f"status={r.status_code}",
        )

        if ok:
            bad_wf_id = str(r.json()["id"])
            r2 = await self.client.post(
                f"/workflows/{bad_wf_id}/run",
                json={"trigger_data": {}},
                headers=self._api_key_headers(),
            )
            run_ok = r2.status_code in (200, 201)
            if run_ok:
                exec_id = str(r2.json()["id"])
                final_status = None
                for _ in range(POLL_MAX_SECONDS):
                    r3 = await self.client.get(
                        f"/executions/{exec_id}", headers=self._api_key_headers()
                    )
                    if r3.status_code == 200:
                        s = r3.json().get("status")
                        if s in ("completed", "failed", "cancelled", "timed_out"):
                            final_status = s
                            break
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                self._record(
                    "bad-ref execution fails gracefully",
                    final_status == "failed",
                    f"final_status={final_status}",
                )

    async def test_cancel_execution(self):
        """POST /executions/{id}/cancel — cancel a recently triggered execution."""
        if not self.workflow_id:
            self._skip("POST /executions/{id}/cancel", "no workflow_id")
            return

        # Trigger a fresh execution to cancel
        r = await self.client.post(
            f"/workflows/{self.workflow_id}/run",
            json={"trigger_data": {"source": "cancel-test"}},
            headers=self._api_key_headers(),
        )
        if r.status_code not in (200, 201):
            self._skip("POST /executions/{id}/cancel", f"trigger failed: {r.status_code}")
            return

        exec_id = str(r.json()["id"])
        r2 = await self.client.post(
            f"/executions/{exec_id}/cancel",
            headers=self._api_key_headers(),
        )
        ok = r2.status_code == 200
        status_after = r2.json().get("status") if ok else None
        self._record(
            "POST /executions/{id}/cancel",
            ok,
            f"status={r2.status_code} exec_status={status_after}",
        )

    # ── Phase D: Sub-workflow ─────────────────────────────────────────────────

    async def test_create_subworkflow(self):
        """Create a parent workflow that references a child workflow."""
        # Create child first
        child_def: Dict[str, Any] = {
            "name": "child-wf",
            "steps": [{"id": "child-step", "type": "plan", "goal": "child task"}],
        }
        r = await self.client.post(
            "/workflows",
            json={"name": "child-wf", "definition": child_def},
            headers=self._api_key_headers(),
        )
        if r.status_code not in (200, 201):
            self._skip("sub-workflow test", f"child creation failed: {r.status_code}")
            return
        self.child_workflow_id = str(r.json()["id"])

        # Create parent that embeds the child
        parent_def: Dict[str, Any] = {
            "name": "parent-wf",
            "steps": [
                {
                    "id": "sub",
                    "type": "sub_workflow",
                    "workflow": self.child_workflow_id,
                    "input": {},
                }
            ],
        }
        r2 = await self.client.post(
            "/workflows",
            json={"name": "parent-wf", "definition": parent_def},
            headers=self._api_key_headers(),
        )
        ok = r2.status_code in (200, 201)
        if ok:
            self.parent_workflow_id = str(r2.json()["id"])
        self._record(
            "POST /workflows (parent + child sub-workflow)",
            ok,
            f"status={r2.status_code}",
        )

    async def test_run_subworkflow(self):
        """Trigger parent workflow and verify both parent and child executions are tracked."""
        if not self.parent_workflow_id:
            self._skip("run parent + child executions", "no parent_workflow_id")
            return

        r = await self.client.post(
            f"/workflows/{self.parent_workflow_id}/run",
            json={"trigger_data": {}},
            headers=self._api_key_headers(),
        )
        if r.status_code not in (200, 201):
            self._record(
                "sub-workflow: trigger parent",
                False,
                f"status={r.status_code} body={r.text[:120]}",
            )
            return

        parent_exec_id = str(r.json()["id"])

        # Poll parent to terminal
        final_status = None
        for _ in range(POLL_MAX_SECONDS):
            r2 = await self.client.get(
                f"/executions/{parent_exec_id}", headers=self._api_key_headers()
            )
            if r2.status_code == 200:
                s = r2.json().get("status")
                if s in ("completed", "failed", "cancelled", "timed_out"):
                    final_status = s
                    break
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        # List all executions and check for child execution (parent_execution_id set)
        r3 = await self.client.get(
            "/executions",
            params={"workflow_id": self.child_workflow_id},
            headers=self._api_key_headers(),
        )
        child_execs = r3.json().get("items", []) if r3.status_code == 200 else []
        ok = final_status is not None and len(child_execs) >= 1
        self._record(
            "sub-workflow: parent + child execution tracked",
            ok,
            f"parent_final={final_status} child_execs={len(child_execs)}",
        )

    # ── 404 / auth edge cases ─────────────────────────────────────────────────

    async def test_get_nonexistent_workflow(self):
        """GET /workflows/{id} for unknown ID returns 404."""
        fake_id = str(uuid.uuid4())
        r = await self.client.get(f"/workflows/{fake_id}", headers=self._api_key_headers())
        ok = r.status_code == 404
        self._record("GET /workflows/{id} (not found → 404)", ok, f"status={r.status_code}")

    async def test_get_nonexistent_execution(self):
        """GET /executions/{id} for unknown ID returns 404."""
        fake_id = str(uuid.uuid4())
        r = await self.client.get(f"/executions/{fake_id}", headers=self._api_key_headers())
        ok = r.status_code == 404
        self._record("GET /executions/{id} (not found → 404)", ok, f"status={r.status_code}")

    async def test_workflow_endpoint_requires_auth(self):
        """GET /workflows without credentials returns 401/403."""
        r = await self.client.get("/workflows")
        ok = r.status_code in (401, 403, 422)
        self._record("GET /workflows (no auth → 401/403)", ok, f"status={r.status_code}")

    # ── Runner ────────────────────────────────────────────────────────────────

    async def run_all(self):
        print(f"\nRunning new orchestrator tests against {self.base_url}\n")
        await self._bootstrap()

        print("\n── Phase A: Basic workflow lifecycle ──")
        await self.test_create_simple_workflow()
        await self.test_get_workflow()
        await self.test_list_workflows()
        await self.test_trigger_execution()
        await self.test_get_execution_status()
        await self.test_get_process_table()

        print("\n── Phase B: DAG features ──")
        await self.test_create_parallel_workflow()
        await self.test_create_conditional_workflow()
        await self.test_trigger_conditional_and_check_skipped()

        print("\n── Phase C: Error handling ──")
        await self.test_create_workflow_bad_reference()
        await self.test_cancel_execution()

        print("\n── Phase D: Sub-workflow ──")
        await self.test_create_subworkflow()
        await self.test_run_subworkflow()

        print("\n── Edge cases ──")
        await self.test_get_nonexistent_workflow()
        await self.test_get_nonexistent_execution()
        await self.test_workflow_endpoint_requires_auth()

        await self.client.aclose()
        self._print_summary()

    def _print_summary(self):
        total = len(self.results)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = total - passed
        print(f"\n{'='*60}")
        print(f"  Results: {passed}/{total} passed, {failed} failed")
        if failed:
            print("\n  Failed tests:")
            for name, ok, detail in self.results:
                if not ok:
                    print(f"    - {name}: {detail}")
        print(f"{'='*60}\n")
        if failed:
            sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="New orchestrator end-to-end tests")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()

    runner = NewOrchestratorTestRunner(args.base_url)
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
