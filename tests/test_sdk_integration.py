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
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

_SDK_SRC = str(Path(__file__).resolve().parent.parent.parent / "intuno_sdk" / "src")
if _SDK_SRC not in sys.path:
    sys.path.insert(0, _SDK_SRC)

from intuno_sdk.client import AsyncIntunoClient, IntunoClient
from intuno_sdk.exceptions import IntunoError, InvocationError
from intuno_sdk.models import Agent, Conversation, InvokeResult, Message, TaskResult
from tests.test_utils import build_sample_input

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"


class SDKTestRunner:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.results: list[tuple[str, bool, str]] = []

        self.agent_id_str: str | None = None
        self.first_agent_input: Dict[str, Any] = {}

        # For conversation API tests (set after invoke with external_user_id)
        self.conv_id: str | None = None
        self.conv_external_user: str = "sdk-conv-api-test"

    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = PASS if passed else FAIL
        print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((name, passed, detail))

    def _skip(self, name: str, reason: str = ""):
        print(f"  [{SKIP}] {name}" + (f"  ({reason})" if reason else ""))

    def _pick_agent(self, agents: List[Agent]):
        """Pick an agent and sample input from discovered agents.

        Prefers agents whose input_schema has a text-like field (message/query/text)
        so the invoke payload is compatible with the wisdom-agents chat endpoint.
        """
        if not agents:
            return

        TEXT_FIELDS = {"message", "query", "text"}

        for agent in agents:
            props = set((agent.input_schema or {}).get("properties", {}).keys())
            if props & TEXT_FIELDS:
                self.agent_id_str = agent.agent_id
                self.first_agent_input = build_sample_input(agent.input_schema or {})
                return

        agent = agents[0]
        self.agent_id_str = agent.agent_id
        self.first_agent_input = build_sample_input(agent.input_schema or {})

    # ── Sync client tests ──────────────────────────────────────────────

    def test_sync_discover(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agents = client.discover(query="assistant help", limit=5)
            ok = isinstance(agents, list)
            self._record(
                "sync discover()",
                ok,
                f"found={len(agents)}",
            )
            return agents

    def test_sync_invoke(self, agents: list[Agent]):
        if not agents or not self.agent_id_str:
            self._skip("sync agent.invoke()", "no agents from discover")
            return
        agent = agents[0]

        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agent._client = client
            try:
                result = agent.invoke(
                    input_data=self.first_agent_input,
                )
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
            self._skip("sync invoke(external_user_id=bob)", "no agent")
            return
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                result = client.invoke(
                    agent_id=self.agent_id_str,
                    input_data=self.first_agent_input,
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
            agents = await client.discover(query="assistant help", limit=5)
            ok = isinstance(agents, list)
            self._record("async discover()", ok, f"found={len(agents)}")
            return agents

    async def test_async_invoke(self, agents: list[Agent]):
        if not agents or not self.agent_id_str:
            self._skip("async agent.ainvoke()", "no agents from discover")
            return
        agent = agents[0]

        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            agent._client = client
            try:
                result = await agent.ainvoke(
                    input_data=self.first_agent_input,
                )
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
            self._skip("async ainvoke() shared conversation", "no agent")
            return
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                r1 = await client.ainvoke(
                    agent_id=self.agent_id_str,
                    input_data=self.first_agent_input,
                    external_user_id=self.conv_external_user,
                )
                conv_id = getattr(r1, "conversation_id", None)
                if conv_id:
                    self.conv_id = str(conv_id)
                    r2 = await client.ainvoke(
                        agent_id=self.agent_id_str,
                        input_data=self.first_agent_input,
                        conversation_id=conv_id,
                        external_user_id=self.conv_external_user,
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
                        f"no conversation_id returned, r1.success={r1.success}",
                    )
            except Exception as e:
                self._record("async ainvoke() shared conversation", False, f"Error: {e}")

    # ── Task API tests ─────────────────────────────────────────────────

    def test_sync_create_task(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                result = client.create_task(
                    goal="Perform a simple task",
                    input_data=self.first_agent_input,
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
                    goal="Perform a simple async task",
                    input_data=self.first_agent_input,
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

    # ── Discovery (list_new_agents, list_trending_agents) ────────────────

    def test_sync_list_new_agents(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                agents = client.list_new_agents(days=30, limit=10)
                ok = isinstance(agents, list) and all(isinstance(a, Agent) for a in agents)
                self._record("sync list_new_agents()", ok, f"found={len(agents)}")
            except Exception as e:
                self._record("sync list_new_agents()", False, f"Error: {e}")

    def test_sync_list_trending_agents(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                agents = client.list_trending_agents(window_days=7, limit=10)
                ok = isinstance(agents, list) and all(isinstance(a, Agent) for a in agents)
                self._record("sync list_trending_agents()", ok, f"found={len(agents)}")
            except Exception as e:
                self._record("sync list_trending_agents()", False, f"Error: {e}")

    async def test_async_list_new_agents(self):
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                agents = await client.list_new_agents(days=30, limit=10)
                ok = isinstance(agents, list) and all(isinstance(a, Agent) for a in agents)
                self._record("async list_new_agents()", ok, f"found={len(agents)}")
            except Exception as e:
                self._record("async list_new_agents()", False, f"Error: {e}")

    async def test_async_list_trending_agents(self):
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                agents = await client.list_trending_agents(window_days=7, limit=10)
                ok = isinstance(agents, list) and all(isinstance(a, Agent) for a in agents)
                self._record("async list_trending_agents()", ok, f"found={len(agents)}")
            except Exception as e:
                self._record("async list_trending_agents()", False, f"Error: {e}")

    # ── Conversation API ────────────────────────────────────────────────

    def test_sync_list_conversations(self):
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                conversations = client.list_conversations(external_user_id=self.conv_external_user)
                ok = isinstance(conversations, list) and all(isinstance(c, Conversation) for c in conversations)
                has_our_conv = self.conv_id and any(str(c.id) == self.conv_id for c in conversations)
                self._record(
                    "sync list_conversations()",
                    ok and (has_our_conv if self.conv_id else True),
                    f"found={len(conversations)} has_our_conv={has_our_conv}",
                )
            except Exception as e:
                self._record("sync list_conversations()", False, f"Error: {e}")

    def test_sync_get_conversation(self):
        if not self.conv_id:
            self._skip("sync get_conversation()", "no conversation from prior invoke")
            return
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                conv = client.get_conversation(self.conv_id)
                ok = isinstance(conv, Conversation) and str(conv.id) == self.conv_id
                self._record("sync get_conversation()", ok, f"id={conv.id}")
            except Exception as e:
                self._record("sync get_conversation()", False, f"Error: {e}")

    def test_sync_get_messages(self):
        if not self.conv_id:
            self._skip("sync get_messages()", "no conversation from prior invoke")
            return
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                messages = client.get_messages(self.conv_id, limit=20)
                ok = isinstance(messages, list) and all(isinstance(m, Message) for m in messages)
                self._record("sync get_messages()", ok, f"found={len(messages)}")
            except Exception as e:
                self._record("sync get_messages()", False, f"Error: {e}")

    def test_sync_get_message(self):
        if not self.conv_id:
            self._skip("sync get_message()", "no conversation from prior invoke")
            return
        with IntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                messages = client.get_messages(self.conv_id, limit=1)
                if not messages:
                    self._skip("sync get_message()", "no messages in conversation")
                    return
                msg_id = str(messages[0].id)
                msg = client.get_message(self.conv_id, msg_id)
                ok = isinstance(msg, Message) and str(msg.id) == msg_id
                self._record("sync get_message()", ok, f"id={msg.id} role={msg.role}")
            except Exception as e:
                self._record("sync get_message()", False, f"Error: {e}")

    async def test_async_list_conversations(self):
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                conversations = await client.list_conversations(external_user_id=self.conv_external_user)
                ok = isinstance(conversations, list) and all(isinstance(c, Conversation) for c in conversations)
                has_our_conv = self.conv_id and any(str(c.id) == self.conv_id for c in conversations)
                self._record(
                    "async list_conversations()",
                    ok and (has_our_conv if self.conv_id else True),
                    f"found={len(conversations)} has_our_conv={has_our_conv}",
                )
            except Exception as e:
                self._record("async list_conversations()", False, f"Error: {e}")

    async def test_async_get_conversation(self):
        if not self.conv_id:
            self._skip("async get_conversation()", "no conversation from prior invoke")
            return
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                conv = await client.get_conversation(self.conv_id)
                ok = isinstance(conv, Conversation) and str(conv.id) == self.conv_id
                self._record("async get_conversation()", ok, f"id={conv.id}")
            except Exception as e:
                self._record("async get_conversation()", False, f"Error: {e}")

    async def test_async_get_messages(self):
        if not self.conv_id:
            self._skip("async get_messages()", "no conversation from prior invoke")
            return
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                messages = await client.get_messages(self.conv_id, limit=20)
                ok = isinstance(messages, list) and all(isinstance(m, Message) for m in messages)
                self._record("async get_messages()", ok, f"found={len(messages)}")
            except Exception as e:
                self._record("async get_messages()", False, f"Error: {e}")

    async def test_async_get_message(self):
        if not self.conv_id:
            self._skip("async get_message()", "no conversation from prior invoke")
            return
        async with AsyncIntunoClient(api_key=self.api_key, base_url=self.base_url) as client:
            try:
                messages = await client.get_messages(self.conv_id, limit=1)
                if not messages:
                    self._skip("async get_message()", "no messages in conversation")
                    return
                msg_id = str(messages[0].id)
                msg = await client.get_message(self.conv_id, msg_id)
                ok = isinstance(msg, Message) and str(msg.id) == msg_id
                self._record("async get_message()", ok, f"id={msg.id} role={msg.role}")
            except Exception as e:
                self._record("async get_message()", False, f"Error: {e}")

    # ── Runner ─────────────────────────────────────────────────────────

    async def run_all(self):
        print(f"\n{'='*60}")
        print(f"  Intuno SDK Integration Tests")
        print(f"  Target: {self.base_url}")
        print(f"  (using existing agents, no registration/deletion)")
        print(f"{'='*60}\n")

        print("── Sync Client ──")
        agents = self.test_sync_discover()
        self._pick_agent(agents)
        print(f"     using agent={self.agent_id_str} input={self.first_agent_input}")
        self.test_sync_invoke(agents)
        self.test_sync_invoke_with_external_user()

        print("\n── Async Client ──")
        async_agents = await self.test_async_discover()
        await self.test_async_invoke(async_agents)
        await self.test_async_invoke_with_conversation()

        print("\n── Discovery (new/trending) ──")
        self.test_sync_list_new_agents()
        self.test_sync_list_trending_agents()
        await self.test_async_list_new_agents()
        await self.test_async_list_trending_agents()

        print("\n── Task API ──")
        self.test_sync_create_task()
        await self.test_async_create_task_poll()

        print("\n── Conversation API ──")
        self.test_sync_list_conversations()
        self.test_sync_get_conversation()
        self.test_sync_get_messages()
        self.test_sync_get_message()
        await self.test_async_list_conversations()
        await self.test_async_get_conversation()
        await self.test_async_get_messages()
        await self.test_async_get_message()

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
