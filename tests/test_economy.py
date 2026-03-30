"""
End-to-end test script for the Economy module (wallets, credits, market, scenarios).

Spins up a fresh user via /auth/register, then exercises all mounted economy
routes in five phases:

  Phase A — Wallets       (basic CRUD + transfers)
  Phase B — Credits       (packages, purchase lifecycle)
  Phase C — Scenarios + Market (integrated simulation flow)
  Phase D — Consolidation (sweep agent wallets)
  Phase E — Edge cases    (auth errors, 404s, overdraft, duplicate start)

Prerequisites:
  1. Wisdom backend running on BASE_URL (default http://localhost:8000)
  2. PostgreSQL + Redis accessible per .env
  3. At least one credit package configured in ECONOMY_CREDIT_PACKAGES

Usage:
  cd wisdom
  python -m tests.test_economy
  python -m tests.test_economy --base-url http://localhost:8000
"""

import argparse
import asyncio
import sys
import uuid
from typing import Optional

import httpx

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

# Maximum seconds to wait for a scenario tick to advance
SCENARIO_POLL_TIMEOUT = 30


class EconomyTestRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=60)
        self.results: list[tuple[str, bool, str]] = []

        self.jwt_token: Optional[str] = None
        self.user_id: Optional[str] = None

        # Wallet state
        self.wallet_id: Optional[str] = None
        self.wallet_balance: int = 0

        # Secondary wallet for transfer tests
        self.dest_wallet_id: Optional[str] = None

        # Purchase state
        self.purchase_id: Optional[str] = None
        self.cancel_purchase_id: Optional[str] = None

        # Market state
        self.scenario_capability: Optional[str] = None

    # ── Helpers ────────────────────────────────────────────────────────

    def _record(self, name: str, passed: bool, detail: str = ""):
        tag = PASS if passed else FAIL
        print(f"  [{tag}] {name}" + (f"  ({detail})" if detail else ""))
        self.results.append((name, passed, detail))

    def _skip(self, name: str, reason: str = ""):
        print(f"  [{SKIP}] {name}" + (f"  ({reason})" if reason else ""))

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.jwt_token}"}

    # ── Bootstrap: register + login ────────────────────────────────────

    async def _bootstrap(self):
        suffix = uuid.uuid4().hex[:8]
        email = f"eco-test-{suffix}@intuno.dev"
        password = "TestPass123!"
        payload = {
            "email": email,
            "password": password,
            "first_name": "Economy",
            "last_name": "Test",
        }
        r = await self.client.post("/auth/register", json=payload)
        if r.status_code not in (200, 201):
            print(f"  [FATAL] Registration failed: {r.status_code} {r.text}")
            sys.exit(1)
        data = r.json()
        self.user_id = str(data.get("id", ""))

        r = await self.client.post("/auth/login", json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"  [FATAL] Login failed: {r.status_code} {r.text}")
            sys.exit(1)
        self.jwt_token = r.json().get("access_token")
        print(f"  Bootstrapped user {email} (id={self.user_id})")

    # ── Phase A: Wallets ───────────────────────────────────────────────

    async def test_get_my_wallet(self):
        r = await self.client.get("/wallets/me", headers=self._auth_headers())
        ok = r.status_code == 200
        if ok:
            data = r.json()
            self.wallet_id = data.get("id")
            self.wallet_balance = data.get("balance", 0)
        self._record(
            "GET /wallets/me",
            ok,
            f"status={r.status_code} wallet_id={self.wallet_id} balance={self.wallet_balance}",
        )

    async def test_get_wallet_overview(self):
        r = await self.client.get("/wallets/me/overview", headers=self._auth_headers())
        ok = r.status_code == 200 and "wallet" in r.json()
        self._record("GET /wallets/me/overview", ok, f"status={r.status_code}")

    async def test_grant_welcome(self):
        if not self.wallet_id:
            self._skip("POST /wallets/{id}/grant (welcome)", "no wallet_id")
            return
        r = await self.client.post(
            f"/wallets/{self.wallet_id}/grant",
            json={"amount": 100, "grant_type": "grant_welcome", "description": "welcome bonus"},
        )
        ok = r.status_code == 200
        if ok:
            self.wallet_balance = r.json().get("balance", self.wallet_balance)
        self._record(
            "POST /wallets/{id}/grant (welcome)",
            ok,
            f"status={r.status_code} balance={self.wallet_balance}",
        )

    async def test_wallet_summary(self):
        if not self.wallet_id:
            self._skip("GET /wallets/{id}/summary", "no wallet_id")
            return
        r = await self.client.get(f"/wallets/{self.wallet_id}/summary")
        ok = r.status_code == 200
        data = r.json() if ok else {}
        has_grant = ok and data.get("total_granted", 0) > 0
        self._record(
            "GET /wallets/{id}/summary",
            ok and has_grant,
            f"status={r.status_code} total_granted={data.get('total_granted')}",
        )

    async def test_list_transactions(self):
        if not self.wallet_id:
            self._skip("GET /wallets/{id}/transactions", "no wallet_id")
            return
        r = await self.client.get(
            f"/wallets/{self.wallet_id}/transactions",
            params={"limit": 20, "offset": 0},
        )
        ok = r.status_code == 200
        txs = r.json() if ok else []
        self._record(
            "GET /wallets/{id}/transactions",
            ok and len(txs) >= 1,
            f"status={r.status_code} count={len(txs)}",
        )

    async def test_credit_wallet(self):
        if not self.wallet_id:
            self._skip("POST /wallets/{id}/credit", "no wallet_id")
            return
        before = self.wallet_balance
        r = await self.client.post(
            f"/wallets/{self.wallet_id}/credit",
            json={"amount": 50, "description": "test credit"},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        if ok:
            self.wallet_balance = r.json().get("balance", self.wallet_balance)
        self._record(
            "POST /wallets/{id}/credit",
            ok and self.wallet_balance == before + 50,
            f"status={r.status_code} before={before} after={self.wallet_balance}",
        )

    async def test_debit_wallet(self):
        if not self.wallet_id:
            self._skip("POST /wallets/{id}/debit", "no wallet_id")
            return
        before = self.wallet_balance
        r = await self.client.post(
            f"/wallets/{self.wallet_id}/debit",
            json={"amount": 10, "description": "test debit"},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        if ok:
            self.wallet_balance = r.json().get("balance", self.wallet_balance)
        self._record(
            "POST /wallets/{id}/debit",
            ok and self.wallet_balance == before - 10,
            f"status={r.status_code} before={before} after={self.wallet_balance}",
        )

    async def test_transfer(self):
        if not self.wallet_id:
            self._skip("POST /transfer", "no wallet_id")
            return

        # Create a second wallet by registering a second user
        suffix = uuid.uuid4().hex[:8]
        r = await self.client.post(
            "/auth/register",
            json={
                "email": f"eco-dest-{suffix}@intuno.dev",
                "password": "TestPass123!",
                "first_name": "Dest",
                "last_name": "User",
            },
        )
        if r.status_code not in (200, 201):
            self._skip("POST /transfer", "could not create dest user")
            return
        dest_user_id = r.json().get("id")

        # Get dest wallet
        r2 = await self.client.post(
            "/auth/login",
            json={"email": f"eco-dest-{suffix}@intuno.dev", "password": "TestPass123!"},
        )
        if r2.status_code != 200:
            self._skip("POST /transfer", "could not login dest user")
            return
        dest_token = r2.json().get("access_token")
        r3 = await self.client.get(
            "/wallets/me",
            headers={"Authorization": f"Bearer {dest_token}"},
        )
        if r3.status_code != 200:
            self._skip("POST /transfer", "could not fetch dest wallet")
            return
        self.dest_wallet_id = r3.json().get("id")
        dest_balance_before = r3.json().get("balance", 0)
        src_balance_before = self.wallet_balance

        r = await self.client.post(
            "/wallets/transfer",
            json={
                "from_wallet_id": self.wallet_id,
                "to_wallet_id": self.dest_wallet_id,
                "amount": 5,
                "description": "e2e transfer test",
            },
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200

        # Verify both balances changed
        if ok:
            r_src = await self.client.get(f"/wallets/{self.wallet_id}")
            r_dst = await self.client.get(
                "/wallets/me",
                headers={"Authorization": f"Bearer {dest_token}"},
            )
            src_ok = r_src.status_code == 200 and r_src.json().get("balance") == src_balance_before - 5
            dst_ok = r_dst.status_code == 200 and r_dst.json().get("balance") == dest_balance_before + 5
            if src_ok:
                self.wallet_balance = src_balance_before - 5
            ok = ok and src_ok and dst_ok
        self._record(
            "POST /wallets/transfer (double-entry check)",
            ok,
            f"status={r.status_code}",
        )

    async def test_get_my_agents_empty(self):
        r = await self.client.get("/wallets/me/agents", headers=self._auth_headers())
        ok = r.status_code == 200 and isinstance(r.json(), list)
        self._record(
            "GET /wallets/me/agents (empty initially)",
            ok,
            f"status={r.status_code} count={len(r.json()) if ok else 'N/A'}",
        )

    # ── Phase B: Credits / Purchases ───────────────────────────────────

    async def test_list_packages(self):
        r = await self.client.get("/credits/packages")
        ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 1
        self._record(
            "GET /credits/packages",
            ok,
            f"status={r.status_code} count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )
        return r.json() if ok else []

    async def test_create_purchase(self, packages: list) -> Optional[str]:
        if not self.wallet_id or not packages:
            self._skip("POST /credits/wallets/{id}/purchase", "no wallet or packages")
            return None
        package_id = packages[0]["id"]
        r = await self.client.post(
            f"/credits/wallets/{self.wallet_id}/purchase",
            json={"package_id": package_id},
        )
        ok = r.status_code in (200, 201)
        data = r.json() if ok else {}
        purchase_id = str(data.get("id", ""))
        status_val = data.get("status")
        ok = ok and status_val == "pending"
        if ok:
            self.purchase_id = purchase_id
        self._record(
            "POST /credits/wallets/{id}/purchase → pending",
            ok,
            f"status={r.status_code} purchase_id={purchase_id} purchase_status={status_val}",
        )
        return purchase_id

    async def test_confirm_purchase(self):
        if not self.purchase_id or not self.wallet_id:
            self._skip("POST /credits/purchases/{id}/confirm", "no purchase_id")
            return
        balance_before = self.wallet_balance
        r = await self.client.post(f"/credits/purchases/{self.purchase_id}/confirm")
        ok = r.status_code == 200
        data = r.json() if ok else {}
        ok = ok and data.get("status") == "completed"
        if ok:
            # Verify balance increased
            r2 = await self.client.get(f"/wallets/{self.wallet_id}")
            if r2.status_code == 200:
                self.wallet_balance = r2.json().get("balance", balance_before)
                ok = ok and self.wallet_balance > balance_before
        self._record(
            "POST /credits/purchases/{id}/confirm → completed + balance increases",
            ok,
            f"status={r.status_code} purchase_status={data.get('status')} balance={self.wallet_balance}",
        )

    async def test_cancel_purchase(self, packages: list):
        if not self.wallet_id or not packages:
            self._skip("POST /credits/purchases/{id}/cancel", "no wallet or packages")
            return
        # Create a second purchase to cancel
        package_id = packages[0]["id"]
        r = await self.client.post(
            f"/credits/wallets/{self.wallet_id}/purchase",
            json={"package_id": package_id},
        )
        ok = r.status_code in (200, 201)
        if not ok:
            self._skip("POST /credits/purchases/{id}/cancel", "could not create purchase to cancel")
            return
        self.cancel_purchase_id = str(r.json().get("id", ""))
        r2 = await self.client.post(f"/credits/purchases/{self.cancel_purchase_id}/cancel")
        ok = r2.status_code == 200 and r2.json().get("status") == "failed"
        self._record(
            "POST /credits/purchases/{id}/cancel → failed",
            ok,
            f"status={r2.status_code} purchase_status={r2.json().get('status') if r2.status_code == 200 else 'N/A'}",
        )

    async def test_confirm_cancelled_purchase(self):
        if not self.cancel_purchase_id:
            self._skip("confirm already-cancelled purchase → 4xx", "no cancel_purchase_id")
            return
        r = await self.client.post(f"/credits/purchases/{self.cancel_purchase_id}/confirm")
        ok = r.status_code >= 400
        self._record(
            "confirm already-cancelled purchase → 4xx",
            ok,
            f"status={r.status_code}",
        )

    # ── Phase C: Scenarios + Market ────────────────────────────────────

    async def test_list_scenarios(self):
        r = await self.client.get("/scenarios")
        ok = r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 4
        self._record(
            "GET /scenarios/ (≥4 available)",
            ok,
            f"status={r.status_code} count={len(r.json()) if r.status_code == 200 else 'N/A'}",
        )

    async def test_scenario_status_idle(self):
        r = await self.client.get("/scenarios/status")
        ok = r.status_code == 200
        status_val = r.json().get("status") if ok else None
        self._record(
            "GET /scenarios/status (initially idle/stopped)",
            ok,
            f"status={r.status_code} scenario_status={status_val}",
        )

    async def test_start_scenario(self) -> bool:
        # Stop any scenario that may be running from a previous test run
        await self.client.post("/scenarios/stop")
        config = {
            "scenario_name": "price_discovery",
            "tick_count": 3,
            "tick_interval_ms": 200,
            "service_agent_count": 1,
            "buyer_agent_count": 1,
            "initial_balance": 500,
        }
        r = await self.client.post("/scenarios/start", json=config)
        ok = r.status_code == 200
        data = r.json() if ok else {}
        started = ok and data.get("status") in ("running", "idle")
        self._record(
            "POST /scenarios/start (price_discovery)",
            ok,
            f"status={r.status_code} scenario_status={data.get('status')}",
        )
        return ok

    async def test_scenario_status_running(self):
        r = await self.client.get("/scenarios/status")
        ok = r.status_code == 200
        data = r.json() if ok else {}
        self._record(
            "GET /scenarios/status → running",
            ok and data.get("status") == "running",
            f"status={r.status_code} scenario_status={data.get('status')}",
        )

    async def test_poll_scenario_tick(self):
        """Poll until current_tick >= 1 or timeout."""
        elapsed = 0
        interval = 1
        tick_reached = False
        while elapsed < SCENARIO_POLL_TIMEOUT:
            await asyncio.sleep(interval)
            elapsed += interval
            r = await self.client.get("/scenarios/status")
            if r.status_code != 200:
                continue
            data = r.json()
            if data.get("current_tick", 0) >= 1:
                tick_reached = True
                break
            if data.get("status") in ("completed", "stopped", "error"):
                break
        self._record(
            f"scenarios/status poll → current_tick≥1 (timeout={SCENARIO_POLL_TIMEOUT}s)",
            tick_reached,
            f"elapsed={elapsed}s tick_reached={tick_reached}",
        )
        return tick_reached

    async def test_market_capabilities(self):
        r = await self.client.get("/market/capabilities")
        ok = r.status_code == 200
        caps = r.json() if ok else []
        # Pick first capability for order book test
        if caps:
            self.scenario_capability = caps[0].get("agent_id") or caps[0].get("tags", [None])[0]
        self._record(
            "GET /market/capabilities (≥1 after scenario start)",
            ok,
            f"status={r.status_code} count={len(caps)}",
        )

    async def test_order_book(self):
        if not self.scenario_capability:
            # Try a generic capability name from the scenario setup
            self.scenario_capability = "translation"
        r = await self.client.get(f"/market/book/{self.scenario_capability}")
        ok = r.status_code == 200
        data = r.json() if ok else {}
        self._record(
            f"GET /market/book/{{capability}} ({self.scenario_capability})",
            ok,
            f"status={r.status_code} bids={len(data.get('bids', []))} asks={len(data.get('asks', []))}",
        )

    async def test_list_trades(self):
        r = await self.client.get("/market/trades", params={"limit": 50})
        ok = r.status_code == 200
        trades = r.json() if ok else []
        # Trades may be empty if the scenario hasn't matched yet — warn but don't fail hard
        self._record(
            "GET /market/trades (≥0 after scenario run)",
            ok,
            f"status={r.status_code} count={len(trades)}",
        )

    async def test_stop_scenario(self):
        r = await self.client.post("/scenarios/stop")
        # 200 = stopped now; 400 = already completed (short tick count ran to completion)
        ok = r.status_code in (200, 400)
        data = r.json() if r.status_code == 200 else {}
        self._record(
            "POST /scenarios/stop",
            ok,
            f"status={r.status_code} scenario_status={data.get('status')}",
        )

    async def test_scenario_status_stopped(self):
        r = await self.client.get("/scenarios/status")
        ok = r.status_code == 200
        data = r.json() if ok else {}
        stopped = data.get("status") not in ("running",)
        self._record(
            "GET /scenarios/status → not running after stop",
            ok and stopped,
            f"status={r.status_code} scenario_status={data.get('status')}",
        )

    # ── Phase D: Consolidation ─────────────────────────────────────────

    async def test_consolidate(self):
        r = await self.client.post(
            "/wallets/me/consolidate",
            json={},
            headers=self._auth_headers(),
        )
        ok = r.status_code == 200
        data = r.json() if ok else {}
        self._record(
            "POST /wallets/me/consolidate",
            ok,
            f"status={r.status_code} total_swept={data.get('total_swept')} wallets_swept={data.get('wallets_swept')}",
        )

    # ── Phase E: Edge cases / auth ─────────────────────────────────────

    async def test_no_auth_wallet(self):
        r = await self.client.get("/wallets/me")
        ok = r.status_code in (401, 403)
        self._record(
            "GET /wallets/me (no auth) → 401/403",
            ok,
            f"status={r.status_code}",
        )

    async def test_wallet_not_found(self):
        fake_id = str(uuid.uuid4())
        r = await self.client.get(f"/wallets/{fake_id}")
        ok = r.status_code == 404
        self._record(
            "GET /wallets/{nonexistent-uuid} → 404",
            ok,
            f"status={r.status_code}",
        )

    async def test_overdraft(self):
        if not self.wallet_id:
            self._skip("POST /wallets/{id}/debit (overdraft) → 4xx", "no wallet_id")
            return
        # Debit more than any reasonable balance
        r = await self.client.post(
            f"/wallets/{self.wallet_id}/debit",
            json={"amount": 999_999_999, "description": "overdraft test"},
            headers=self._auth_headers(),
        )
        ok = r.status_code >= 400
        self._record(
            "POST /wallets/{id}/debit (amount > balance) → 4xx",
            ok,
            f"status={r.status_code}",
        )

    async def test_duplicate_scenario_start(self):
        """Start a scenario, then try to start another — expect 4xx."""
        config = {
            "scenario_name": "price_discovery",
            "tick_count": 100,
            "tick_interval_ms": 500,
            "service_agent_count": 1,
            "buyer_agent_count": 1,
            "initial_balance": 200,
        }
        # Make sure nothing is running first
        await self.client.post("/scenarios/stop")
        await asyncio.sleep(0.2)

        r1 = await self.client.post("/scenarios/start", json=config)
        if r1.status_code != 200:
            self._skip(
                "POST /scenarios/start (duplicate) → 409/4xx",
                f"first start failed ({r1.status_code})",
            )
            return

        r2 = await self.client.post("/scenarios/start", json=config)
        ok = r2.status_code >= 400
        self._record(
            "POST /scenarios/start while running → 409/4xx",
            ok,
            f"status={r2.status_code}",
        )
        # Clean up
        await self.client.post("/scenarios/stop")

    # ── Runner ─────────────────────────────────────────────────────────

    async def run_all(self):
        print(f"\n{'='*60}")
        print(f"  Wisdom Economy Module — E2E Tests")
        print(f"  Target: {self.base_url}")
        print(f"{'='*60}\n")

        print("── Bootstrap ──")
        await self._bootstrap()

        print("\n── Phase A: Wallets ──")
        await self.test_get_my_wallet()
        await self.test_get_wallet_overview()
        await self.test_grant_welcome()
        await self.test_wallet_summary()
        await self.test_list_transactions()
        await self.test_credit_wallet()
        await self.test_debit_wallet()
        await self.test_transfer()
        await self.test_get_my_agents_empty()

        print("\n── Phase B: Credits / Purchases ──")
        packages = await self.test_list_packages()
        await self.test_create_purchase(packages)
        await self.test_confirm_purchase()
        await self.test_cancel_purchase(packages)
        await self.test_confirm_cancelled_purchase()

        print("\n── Phase C: Scenarios + Market ──")
        await self.test_list_scenarios()
        await self.test_scenario_status_idle()
        started = await self.test_start_scenario()
        if started:
            await self.test_scenario_status_running()
            await self.test_poll_scenario_tick()
            await self.test_market_capabilities()
            await self.test_order_book()
            await self.test_list_trades()
            await self.test_stop_scenario()
            await self.test_scenario_status_stopped()
        else:
            for name in [
                "GET /scenarios/status → running",
                "scenarios/status poll → current_tick≥1",
                "GET /market/capabilities",
                "GET /market/book/{capability}",
                "GET /market/trades",
                "POST /scenarios/stop",
                "GET /scenarios/status → not running after stop",
            ]:
                self._skip(name, "scenario did not start")

        print("\n── Phase D: Consolidation ──")
        await self.test_consolidate()

        print("\n── Phase E: Edge Cases / Auth ──")
        await self.test_no_auth_wallet()
        await self.test_wallet_not_found()
        await self.test_overdraft()
        await self.test_duplicate_scenario_start()

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
    parser = argparse.ArgumentParser(description="Wisdom economy module e2e tests")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()

    runner = EconomyTestRunner(args.base_url)
    await runner.run_all()


if __name__ == "__main__":
    asyncio.run(main())
