"""
SDK integration test script — validates the Intuno SDK against a live backend.

Assumes agents are already registered on the server — skips agent
registration/deletion and any other destructive actions.

Prerequisites:
  1. Wisdom backend running on BASE_URL (default http://localhost:8000)
  2. At least one agent already registered in the registry
  3. An API key (personal or integration) — the script can create one for you

Usage:
  cd wisdom
  python -m tests.test_sdk_integration
  python -m tests.test_sdk_integration --api-key "sk-..."
  python -m tests.test_sdk_integration --base-url http://localhost:8000
"""

import argparse
import asyncio
import sys
import uuid

import httpx

sys.path.insert(0, "../intuno_sdk")
from src.intuno_sdk.client import AsyncIntunoClient, IntunoClient
from src.intuno_sdk.exceptions import IntunoError, InvocationError
from src.intuno_sdk.models import Agent, InvokeResult, TaskResult

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"


class SDKTestRunner:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.results: list[tuple[str, bool, str]] = []
        self.agent_id_str: str | None = None

    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = PASS if passed else FAIL
        print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((name, passed, detail))

    def _skip(self, name: str, reason: str = ""):
        print(f"  [{SKIP}] {name}" + (f"  ({reason})" if reason else ""))

    # ── Sync client tests ──────────────────────────────────────────────

    def test_sync_discover(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agents = client.discover(query="calculator math", limit=5)
            ok = isinstance(agents, list)
            has_caps = all(isinstance(a, Agent) and len(a.capabilities) > 0 for a in agents) if agents else True
            self._record(
                "sync discover()",
                ok,
                f"found={len(agents)} all_have_caps={has_caps}",
            )
            return agents

    def test_sync_invoke(self, agents: list[Agent]):
        if not agents:
            self._skip("sync agent.invoke()", "no agents from discover")
            return
        agent = agents[0]
        cap_id = agent.capabilities[0].id if agent.capabilities else None
        if not cap_id:
            self._skip("sync agent.invoke()", "agent has no capabilities")
            return

        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agent._client = client
            try:
                result = agent.invoke(capability_name_or_id=cap_id, input_data={"a": 10, "b": 5})
                ok = isinstance(result, InvokeResult) and result.success
                self._record(
                    "sync agent.invoke()",
                    ok,
                    f"success={result.success} data={result.data} latency={result.latency_ms}ms",
                )
            except InvocationError as e:
                self._record("sync agent.invoke()", False, f"InvocationError: {e}")
            except Exception as e:
                self._record("sync agent.invoke()", False, f"Error: {e}")

    def test_sync_invoke_with_external_user(self):
        if not self.agent_id_str:
            self._skip("sync invoke(external_user_id=bob)", "no agent_id")
            return
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                result = client.invoke(
                    agent_id=self.agent_id_str,
                    capability_id="add",
                    input_data={"a": 100, "b": 200},
                    external_user_id="sdk-test-user-bob",
                )
                ok = isinstance(result, InvokeResult) and result.success
                self._record(
                    "sync invoke(external_user_id=bob)",
                    ok,
                    f"success={result.success} data={result.data}",
                )
            except Exception as e:
                self._record("sync invoke(external_user_id=bob)", False, f"Error: {e}")

    # ── Async client tests ─────────────────────────────────────────────

    async def test_async_discover(self):
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agents = await client.discover(query="calculator math", limit=5)
            ok = isinstance(agents, list)
            self._record("async discover()", ok, f"found={len(agents)}")
            return agents

    async def test_async_invoke(self, agents: list[Agent]):
        if not agents:
            self._skip("async agent.ainvoke()", "no agents from discover")
            return
        agent = agents[0]
        cap_id = agent.capabilities[0].id if agent.capabilities else None
        if not cap_id:
            self._skip("async agent.ainvoke()", "agent has no capabilities")
            return

        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agent._client = client
            try:
                result = await agent.ainvoke(capability_name_or_id=cap_id, input_data={"a": 20, "b": 3})
                ok = isinstance(result, InvokeResult) and result.success
                self._record(
                    "async agent.ainvoke()",
                    ok,
                    f"success={result.success} data={result.data} latency={result.latency_ms}ms",
                )
            except InvocationError as e:
                self._record("async agent.ainvoke()", False, f"InvocationError: {e}")
            except Exception as e:
                self._record("async agent.ainvoke()", False, f"Error: {e}")

    async def test_async_invoke_with_conversation(self):
        if not self.agent_id_str:
            self._skip("async ainvoke() shared conversation", "no agent_id")
            return
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                r1 = await client.ainvoke(
                    agent_id=self.agent_id_str,
                    capability_id="add",
                    input_data={"a": 1, "b": 2},
                    external_user_id="sdk-conv-test-user",
                )
                conv_id = getattr(r1, "conversation_id", None)
                if conv_id:
                    r2 = await client.ainvoke(
                        agent_id=self.agent_id_str,
                        capability_id="multiply",
                        input_data={"a": 3, "b": 4},
                        conversation_id=conv_id,
                        external_user_id="sdk-conv-test-user",
                    )
                    ok = r1.success and r2.success
                    self._record(
                        "async ainvoke() shared conversation",
                        ok,
                        f"conv={conv_id} r1={r1.data} r2={r2.data}",
                    )
                else:
                    ok = r1.success
                    self._record(
                        "async ainvoke() shared conversation",
                        ok,
                        f"no conversation_id returned (field may not be in InvokeResult), r1.success={r1.success}",
                    )
            except Exception as e:
                self._record("async ainvoke() shared conversation", False, f"Error: {e}")

    # ── Task API tests ─────────────────────────────────────────────────

    def test_sync_create_task(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                result = client.create_task(
                    goal="Add two numbers: 50 and 25",
                    input_data={"a": 50, "b": 25},
                )
                ok = isinstance(result, TaskResult)
                self._record(
                    "sync create_task()",
                    ok,
                    f"status={result.status} result={result.result}",
                )
            except Exception as e:
                self._record("sync create_task()", False, f"Error: {e}")

    async def test_async_create_task_poll(self):
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                task = await client.create_task(
                    goal="Multiply two numbers: 8 and 9",
                    input_data={"a": 8, "b": 9},
                    async_mode=True,
                )
                ok_created = isinstance(task, TaskResult) and task.status == "pending"
                self._record("async create_task(async=true)", ok_created, f"id={task.id} status={task.status}")

                if ok_created:
                    for _ in range(10):
                        await asyncio.sleep(1)
                        polled = await client.get_task(task.id)
                        if polled.status in ("completed", "failed", "timeout"):
                            self._record(
                                "async get_task() poll",
                                polled.status == "completed",
                                f"status={polled.status} result={polled.result}",
                            )
                            return
                    self._record("async get_task() poll", False, "timed out waiting")
            except Exception as e:
                self._record("async create_task(async=true)", False, f"Error: {e}")

    # ── Runner ─────────────────────────────────────────────────────────

    async def run_all(self):
        print(f"\n{'='*60}")
        print(f"  Intuno SDK Integration Tests")
        print(f"  Target: {self.base_url}")
        print(f"  (using existing agents, no registration/deletion)")
        print(f"{'='*60}\n")

        print("── Sync Client ──")
        agents = self.test_sync_discover()
        if agents:
            self.agent_id_str = agents[0].agent_id
        self.test_sync_invoke(agents)
        self.test_sync_invoke_with_external_user()

        print("\n── Async Client ──")
        async_agents = await self.test_async_discover()
        await self.test_async_invoke(async_agents)
        await self.test_async_invoke_with_conversation()

        print("\n── Task API ──")
        self.test_sync_create_task()
        await self.test_async_create_task_poll()

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


async def bootstrap_api_key(base_url: str) -> str:
    """Create a test user + API key and return the raw key string."""
    async with httpx.AsyncClient(base_url=base_url, timeout=15) as client:
        suffix = uuid.uuid4().hex[:8]
        email = f"sdk-test-{suffix}@intuno.dev"
        r = await client.post(
            "/auth/register",
            json={"email": email, "password": "SdkTestPass1!", "first_name": "SDK", "last_name": "Test"},
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Could not register user: {r.status_code} {r.text}")
        r2 = await client.post("/auth/login", json={"email": email, "password": "SdkTestPass1!"})
        if r2.status_code != 200:
            raise RuntimeError(f"Could not login: {r2.status_code} {r2.text}")
        token = r2.json()["access_token"]
        r3 = await client.post(
            "/auth/api-keys",
            json={"name": "sdk-test-key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        if r3.status_code not in (200, 201):
            raise RuntimeError(f"Could not create API key: {r3.status_code} {r3.text}")
        return r3.json()["key"]


async def main():
    parser = argparse.ArgumentParser(description="Intuno SDK integration tests")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--api-key", default=None, help="Existing API key; if omitted, creates a new user + key")
    args = parser.parse_args()

    api_key = args.api_key
    if not api_key:
        print(f"No --api-key provided; bootstrapping a test user at {args.base_url} ...")
        api_key = await bootstrap_api_key(args.base_url)
        print(f"  Created API key: {api_key[:8]}...")

    runner = SDKTestRunner(args.base_url, api_key)
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
