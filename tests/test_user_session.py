"""
User session E2E tests — simulates real users interacting with agents.

Uses an OpenAI-powered SimulatedUser to generate contextual messages,
tests multi-turn conversations, external_user_id scoping, session
continuity, and conversation history retrieval.

Prerequisites:
  1. Wisdom backend running on BASE_URL (default http://localhost:8000)
  2. Wisdom-agents running on port 8001 with at least one agent
  3. OPENAI_API_KEY set in .env or environment
  4. PostgreSQL + Qdrant accessible per .env

Usage:
  cd wisdom
  python -m tests.test_user_session
  python -m tests.test_user_session --base-url http://localhost:8000
  python -m tests.test_user_session --openai-key sk-...
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

_SDK_SRC = str(Path(__file__).resolve().parent.parent.parent / "intuno_sdk" / "src")
if _SDK_SRC not in sys.path:
    sys.path.insert(0, _SDK_SRC)

from intuno_sdk.client import AsyncIntunoClient

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

ALICE = "session-test-alice"
BOB = "session-test-bob"


# ---------------------------------------------------------------------------
# Simulated user (OpenAI-powered)
# ---------------------------------------------------------------------------


class SimulatedUser:
    """GPT-powered simulated user that generates contextual messages."""

    def __init__(self, openai_key: str, agent_name: str, agent_description: str):
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(api_key=openai_key)
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.history: List[Dict[str, str]] = []

    async def generate_message(self, agent_response: Optional[str] = None) -> str:
        if agent_response:
            self.history.append({"role": "assistant", "content": agent_response})

        system = (
            f"You are a real user testing an AI agent called '{self.agent_name}'. "
            f"Agent description: {self.agent_description}\n\n"
            "Generate a short, natural user message (1-2 sentences) to send to this agent. "
            "If there is prior conversation, follow up on it naturally. "
            "Do NOT break character — you are the user, not the agent."
        )

        messages = [{"role": "system", "content": system}] + self.history

        try:
            resp = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=100,
                temperature=0.8,
            )
            text = (resp.choices[0].message.content or "").strip()
            self.history.append({"role": "user", "content": text})
            return text
        except Exception:
            fallback = "Can you help me with something related to your area of expertise?"
            self.history.append({"role": "user", "content": fallback})
            return fallback


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


class UserSessionTestRunner:
    def __init__(self, base_url: str, openai_key: str):
        self.base_url = base_url.rstrip("/")
        self.openai_key = openai_key
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60)
        self.results: List[tuple[str, bool, str]] = []

        self.jwt_token: Optional[str] = None
        self.personal_api_key: Optional[str] = None
        self.integration_id: Optional[str] = None
        self.integration_api_key: Optional[str] = None

        self.agent_id_str: Optional[str] = None
        self.agent_name: Optional[str] = None
        self.agent_description: Optional[str] = None
        self.first_cap_id: Optional[str] = None

        self.alice_conv_id: Optional[str] = None
        self.bob_conv_id: Optional[str] = None
        self.alice_turn_count: int = 0
        self.bob_turn_count: int = 0

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

    # ── Setup ──────────────────────────────────────────────────────────

    async def setup(self):
        """Bootstrap user, API keys, integration, and discover an agent."""
        suffix = uuid.uuid4().hex[:8]
        email = f"session-{suffix}@intuno.dev"
        pw = "SessionTestPass1!"

        r = await self.client.post(
            "/auth/register",
            json={"email": email, "password": pw, "first_name": "Session", "last_name": "Tester"},
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Register failed: {r.status_code} {r.text}")

        r = await self.client.post("/auth/login", json={"email": email, "password": pw})
        if r.status_code != 200:
            raise RuntimeError(f"Login failed: {r.status_code} {r.text}")
        self.jwt_token = r.json()["access_token"]

        r = await self.client.post(
            "/auth/api-keys",
            json={"name": "session-personal-key"},
            headers=self._auth_headers(),
        )
        if r.status_code in (200, 201):
            self.personal_api_key = r.json()["key"]

        r = await self.client.post(
            "/integrations",
            json={"name": "Session Test App", "kind": "chat"},
            headers=self._auth_headers(),
        )
        if r.status_code in (200, 201):
            self.integration_id = str(r.json()["id"])

        if self.integration_id:
            r = await self.client.post(
                f"/integrations/{self.integration_id}/api-keys",
                json={"name": "session-integration-key"},
                headers=self._auth_headers(),
            )
            if r.status_code in (200, 201):
                self.integration_api_key = r.json()["key"]

        r = await self.client.get(
            "/registry/agents",
            params={"limit": 10},
            headers=self._auth_headers(),
        )
        if r.status_code == 200:
            agents = r.json()
            if agents:
                agent = agents[0]
                self.agent_id_str = agent["agent_id"]
                self.agent_name = agent["name"]
                self.agent_description = agent.get("description", agent["name"])
                caps = agent.get("capabilities", [])
                if caps:
                    self.first_cap_id = caps[0].get("id") or caps[0].get("capability_id")

        ok = all([
            self.jwt_token, self.personal_api_key, self.integration_api_key,
            self.agent_id_str, self.first_cap_id,
        ])
        self._record(
            "Setup (user, keys, integration, agent)",
            ok,
            f"agent={self.agent_id_str} cap={self.first_cap_id}",
        )
        return ok

    # ── Scenario 1: Alice multi-turn (raw HTTP) ───────────────────────

    async def scenario_alice_multiturn(self):
        """3-turn conversation with Alice via raw HTTP + integration API key."""
        if not self.integration_api_key or not self.agent_id_str or not self.first_cap_id:
            self._skip("Alice multi-turn", "missing setup")
            return

        sim = SimulatedUser(self.openai_key, self.agent_name, self.agent_description)
        conv_id = None
        turns_ok = 0
        last_response: Optional[str] = None

        for turn in range(3):
            user_msg = await sim.generate_message(agent_response=last_response)
            print(f"    [Alice turn {turn + 1}] {user_msg[:80]}...")

            payload: Dict[str, Any] = {
                "agent_id": self.agent_id_str,
                "capability_id": self.first_cap_id,
                "input": {"message": user_msg},
                "external_user_id": ALICE,
            }
            if conv_id:
                payload["conversation_id"] = conv_id

            r = await self.client.post(
                "/broker/invoke",
                json=payload,
                headers=self._api_key_headers(self.integration_api_key),
            )
            data = r.json() if r.status_code == 200 else {}
            success = data.get("success", False)

            if success:
                turns_ok += 1
                resp_data = data.get("data", {})
                last_response = resp_data.get("content") or resp_data.get("result") or str(resp_data)
                returned_conv = data.get("conversation_id")
                if turn == 0:
                    conv_id = returned_conv
                    self.alice_conv_id = str(conv_id) if conv_id else None
                print(f"    [Agent] {str(last_response)[:80]}...")
            else:
                last_response = None
                error = data.get("error", "unknown")
                print(f"    [Agent ERROR] {error}")

        self.alice_turn_count = turns_ok
        all_ok = turns_ok == 3 and self.alice_conv_id is not None
        self._record(
            "Scenario 1: Alice multi-turn (3 turns, raw HTTP)",
            all_ok,
            f"turns_ok={turns_ok}/3 conv_id={self.alice_conv_id}",
        )

    # ── Scenario 2: Bob multi-turn (SDK) ──────────────────────────────

    async def scenario_bob_multiturn_sdk(self):
        """2-turn conversation with Bob via the Intuno SDK."""
        if not self.integration_api_key or not self.agent_id_str or not self.first_cap_id:
            self._skip("Bob multi-turn (SDK)", "missing setup")
            return

        sim = SimulatedUser(self.openai_key, self.agent_name, self.agent_description)
        conv_id = None
        turns_ok = 0
        last_response: Optional[str] = None

        async with AsyncIntunoClient(api_key=self.integration_api_key, base_url=self.base_url) as sdk:
            for turn in range(2):
                user_msg = await sim.generate_message(agent_response=last_response)
                print(f"    [Bob turn {turn + 1}] {user_msg[:80]}...")

                try:
                    result = await sdk.ainvoke(
                        agent_id=self.agent_id_str,
                        capability_id=self.first_cap_id,
                        input_data={"message": user_msg},
                        external_user_id=BOB,
                        conversation_id=conv_id,
                    )
                    turns_ok += 1
                    resp_data = result.data or {}
                    last_response = resp_data.get("content") or resp_data.get("result") or str(resp_data)
                    if turn == 0:
                        conv_id = result.conversation_id
                        self.bob_conv_id = conv_id
                    print(f"    [Agent] {str(last_response)[:80]}...")
                except Exception as e:
                    last_response = None
                    print(f"    [SDK ERROR] {e}")

        self.bob_turn_count = turns_ok
        all_ok = turns_ok == 2 and self.bob_conv_id is not None
        self._record(
            "Scenario 2: Bob multi-turn (2 turns, SDK)",
            all_ok,
            f"turns_ok={turns_ok}/2 conv_id={self.bob_conv_id}",
        )

    # ── Scenario 3: External user isolation ───────────────────────────

    async def scenario_external_user_isolation(self):
        """Verify Alice and Bob see only their own conversations."""
        if not self.alice_conv_id and not self.bob_conv_id:
            self._skip("External user isolation", "no conversations created")
            return

        r_alice = await self.client.get(
            "/conversations",
            params={"external_user_id": ALICE},
            headers=self._auth_headers(),
        )
        r_bob = await self.client.get(
            "/conversations",
            params={"external_user_id": BOB},
            headers=self._auth_headers(),
        )

        alice_convs = r_alice.json() if r_alice.status_code == 200 else []
        bob_convs = r_bob.json() if r_bob.status_code == 200 else []

        alice_ids = {str(c["id"]) for c in alice_convs}
        bob_ids = {str(c["id"]) for c in bob_convs}

        alice_only = all(c.get("external_user_id") == ALICE for c in alice_convs)
        bob_only = all(c.get("external_user_id") == BOB for c in bob_convs)
        no_overlap = alice_ids.isdisjoint(bob_ids)

        alice_has_her = self.alice_conv_id in alice_ids if self.alice_conv_id else True
        bob_has_his = self.bob_conv_id in bob_ids if self.bob_conv_id else True

        ok = alice_only and bob_only and no_overlap and alice_has_her and bob_has_his
        self._record(
            "Scenario 3: External user isolation",
            ok,
            f"alice_convs={len(alice_convs)} bob_convs={len(bob_convs)} "
            f"alice_only={alice_only} bob_only={bob_only} no_overlap={no_overlap}",
        )

    # ── Scenario 4: Conversation history and messages ─────────────────

    async def scenario_conversation_history(self):
        """Verify conversation detail, messages, and logs for Alice's conversation."""
        if not self.alice_conv_id:
            self._skip("Conversation history", "no alice conversation")
            return

        r_conv = await self.client.get(
            f"/conversations/{self.alice_conv_id}",
            headers=self._auth_headers(),
        )
        conv_ok = r_conv.status_code == 200
        conv_data = r_conv.json() if conv_ok else {}
        ext_user_match = conv_data.get("external_user_id") == ALICE
        self._record(
            "Scenario 4a: GET conversation detail",
            conv_ok and ext_user_match,
            f"status={r_conv.status_code} external_user_id={conv_data.get('external_user_id')}",
        )

        r_msgs = await self.client.get(
            f"/conversations/{self.alice_conv_id}/messages",
            headers=self._auth_headers(),
        )
        msgs_ok = r_msgs.status_code == 200
        messages = r_msgs.json() if msgs_ok else []
        has_messages = len(messages) > 0
        self._record(
            "Scenario 4b: GET conversation messages",
            msgs_ok and has_messages,
            f"message_count={len(messages)} expected_min={self.alice_turn_count * 2}",
        )

        if messages:
            timestamps = [m.get("created_at", "") for m in messages]
            is_ordered = timestamps == sorted(timestamps)
            self._record(
                "Scenario 4c: Messages in chronological order",
                is_ordered,
                f"ordered={is_ordered}",
            )

        r_logs = await self.client.get(
            f"/conversations/{self.alice_conv_id}/logs",
            headers=self._auth_headers(),
        )
        logs_ok = r_logs.status_code == 200
        logs = r_logs.json() if logs_ok else []
        self._record(
            "Scenario 4d: GET conversation invocation logs",
            logs_ok and len(logs) > 0,
            f"log_count={len(logs)}",
        )

    # ── Scenario 5: Task with conversation context ────────────────────

    async def scenario_task_with_context(self):
        """Create a task referencing Alice's conversation and poll for result."""
        if not self.personal_api_key:
            self._skip("Task with conversation context", "no API key")
            return

        payload: Dict[str, Any] = {
            "goal": "Summarize the conversation so far",
            "input": {"message": "Please summarize what we discussed"},
        }
        if self.alice_conv_id:
            payload["conversation_id"] = self.alice_conv_id

        r = await self.client.post(
            "/tasks",
            json=payload,
            headers=self._api_key_headers(self.personal_api_key),
        )
        ok_created = r.status_code in (200, 201)
        data = r.json() if ok_created else {}
        task_id = data.get("id") or data.get("task_id")

        self._record(
            "Scenario 5a: Create task with conversation context",
            ok_created and task_id is not None,
            f"status={r.status_code} task_id={task_id}",
        )

        if not task_id:
            return

        r_get = await self.client.get(
            f"/tasks/{task_id}",
            headers=self._api_key_headers(self.personal_api_key),
        )
        get_ok = r_get.status_code == 200
        task_data = r_get.json() if get_ok else {}
        self._record(
            "Scenario 5b: GET task result",
            get_ok,
            f"task_status={task_data.get('status', 'N/A')} result={str(task_data.get('result', 'N/A'))[:80]}",
        )

    # ── Runner ─────────────────────────────────────────────────────────

    async def run_all(self):
        print("\n" + "=" * 60)
        print("  User Session E2E Tests")
        print(f"  Target: {self.base_url}")
        print("=" * 60 + "\n")

        print("── Setup ──")
        ok = await self.setup()
        if not ok:
            print("\n  Setup failed — cannot continue.")
            await self.client.aclose()
            self._print_summary()
            return

        print("\n── Scenario 1: Alice multi-turn (raw HTTP) ──")
        await self.scenario_alice_multiturn()

        print("\n── Scenario 2: Bob multi-turn (SDK) ──")
        await self.scenario_bob_multiturn_sdk()

        print("\n── Scenario 3: External user isolation ──")
        await self.scenario_external_user_isolation()

        print("\n── Scenario 4: Conversation history ──")
        await self.scenario_conversation_history()

        print("\n── Scenario 5: Task with conversation context ──")
        await self.scenario_task_with_context()

        await self.client.aclose()
        self._print_summary()

    def _print_summary(self):
        total = len(self.results)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = total - passed
        print("\n" + "=" * 60)
        print(f"  Results: {passed}/{total} passed, {failed} failed")
        if failed:
            print("\n  Failed tests:")
            for name, ok, detail in self.results:
                if not ok:
                    print(f"    - {name}: {detail}")
        print("=" * 60 + "\n")
        if failed:
            sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_openai_key(cli_key: Optional[str]) -> str:
    """Resolve OpenAI key from CLI arg, env, or .env file."""
    if cli_key:
        return cli_key
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("OPENAI_API_KEY not found in args, environment, or .env")


async def main():
    parser = argparse.ArgumentParser(description="User session E2E tests")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--openai-key", default=None, help="OpenAI API key (or set OPENAI_API_KEY)")
    args = parser.parse_args()

    openai_key = _load_openai_key(args.openai_key)
    runner = UserSessionTestRunner(args.base_url, openai_key)
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
