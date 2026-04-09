"""Integration tests for communication networks and multi-directional orchestration.

These tests exercise the full network lifecycle: creating networks,
adding participants, exchanging messages and mailbox items, verifying
shared context, and importing A2A agents.

Requires a running backend at BASE_URL (default: http://localhost:8000).
Mark: integration (auto-applied by conftest.py).

Run:
    pytest tests/test_networks.py -v
    pytest tests/test_networks.py -v -k "test_network_lifecycle"
"""

import asyncio
import os
import uuid

import httpx
import pytest

BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
TIMEOUT = 15


# ── Helpers ──────────────────────────────────────────────────────────


async def register_and_login(client: httpx.AsyncClient) -> str:
    """Register a test user and return a JWT token."""
    email = f"test-net-{uuid.uuid4().hex[:8]}@test.local"
    password = "TestPass123!"

    await client.post(
        f"{BASE_URL}/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": "Net",
            "last_name": "Test",
        },
    )
    resp = await client.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def register_test_agent(
    client: httpx.AsyncClient, token: str, name: str
) -> dict:
    """Register a simple test agent and return its data."""
    resp = await client.post(
        f"{BASE_URL}/registry/agents",
        headers=auth(token),
        json={
            "name": name,
            "description": f"Test agent for network integration: {name}",
            "endpoint": f"https://httpbin.org/post",
            "tags": ["test", "network"],
        },
    )
    assert resp.status_code in (200, 201), f"Agent registration failed: {resp.text}"
    return resp.json()


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        yield c


@pytest.fixture
async def authed(client):
    """Return (client, token) tuple."""
    token = await register_and_login(client)
    return client, token


# ── Network Lifecycle ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_network_lifecycle(authed):
    """Create a network, add participants, exchange messages, verify context."""
    client, token = authed
    headers = auth(token)

    # 1. Create network
    resp = await client.post(
        f"{BASE_URL}/networks",
        headers=headers,
        json={"name": "Test Mesh Network", "topology_type": "mesh"},
    )
    assert resp.status_code == 201, f"Create network failed: {resp.text}"
    network = resp.json()
    network_id = network["id"]
    assert network["name"] == "Test Mesh Network"
    assert network["topology_type"] == "mesh"
    assert network["status"] == "active"

    # 2. List networks
    resp = await client.get(f"{BASE_URL}/networks", headers=headers)
    assert resp.status_code == 200
    networks = resp.json()
    assert any(n["id"] == network_id for n in networks)

    # 3. Add participants (with polling since we don't have real callback URLs)
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={
            "name": "Alice",
            "participant_type": "persona",
            "polling_enabled": True,
        },
    )
    assert resp.status_code == 201, f"Add participant failed: {resp.text}"
    alice = resp.json()
    alice_id = alice["id"]

    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={
            "name": "Bob",
            "participant_type": "persona",
            "polling_enabled": True,
        },
    )
    assert resp.status_code == 201
    bob = resp.json()
    bob_id = bob["id"]

    # 4. List participants
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/participants", headers=headers
    )
    assert resp.status_code == 200
    participants = resp.json()
    assert len(participants) == 2
    names = {p["name"] for p in participants}
    assert names == {"Alice", "Bob"}

    # 5. Send a message (Alice → Bob)
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/send",
        headers=headers,
        json={
            "sender_participant_id": alice_id,
            "recipient_participant_id": bob_id,
            "content": "Hey Bob, what do you think about the proposal?",
        },
    )
    assert resp.status_code == 201, f"Send message failed: {resp.text}"
    msg1 = resp.json()
    assert msg1["channel_type"] == "message"
    assert msg1["sender_participant_id"] == alice_id

    # 6. Send to mailbox (Bob → Alice)
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/mailbox",
        headers=headers,
        json={
            "sender_participant_id": bob_id,
            "recipient_participant_id": alice_id,
            "content": "I'll review it tonight and get back to you.",
        },
    )
    assert resp.status_code == 201
    msg2 = resp.json()
    assert msg2["channel_type"] == "mailbox"

    # 7. Check inbox (Alice should see Bob's mailbox message)
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/inbox/{alice_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    inbox = resp.json()
    assert len(inbox) >= 1

    # 8. Check shared context
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/context",
        headers=headers,
    )
    assert resp.status_code == 200
    context = resp.json()
    assert len(context["entries"]) >= 2
    senders = {e["sender"] for e in context["entries"]}
    assert "Alice" in senders
    assert "Bob" in senders

    # 9. List messages
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/messages",
        headers=headers,
    )
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) >= 2

    # 10. Acknowledge messages
    message_ids = [m["id"] for m in messages[:1]]
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/ack",
        headers=headers,
        json={"message_ids": message_ids},
    )
    assert resp.status_code == 200
    assert resp.json()["acknowledged"] == 1

    # 11. Update network
    resp = await client.patch(
        f"{BASE_URL}/networks/{network_id}",
        headers=headers,
        json={"name": "Updated Mesh Network"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Mesh Network"

    # 12. Remove participant
    resp = await client.delete(
        f"{BASE_URL}/networks/{network_id}/participants/{bob_id}",
        headers=headers,
    )
    assert resp.status_code == 204

    # 13. Verify Bob is removed
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/participants", headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 14. Delete network
    resp = await client.delete(
        f"{BASE_URL}/networks/{network_id}", headers=headers
    )
    assert resp.status_code == 204


# ── Callback (Bidirectional) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_callback_bidirectional(authed):
    """External agent pushes a message back via the callback endpoint."""
    client, token = authed
    headers = auth(token)

    # Create network + participants
    resp = await client.post(
        f"{BASE_URL}/networks",
        headers=headers,
        json={"name": "Callback Test Network"},
    )
    network_id = resp.json()["id"]

    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={"name": "Agent A", "polling_enabled": True},
    )
    agent_a_id = resp.json()["id"]

    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={"name": "Agent B", "polling_enabled": True},
    )
    agent_b_id = resp.json()["id"]

    # Agent A sends a message
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/send",
        headers=headers,
        json={
            "sender_participant_id": agent_a_id,
            "recipient_participant_id": agent_b_id,
            "content": "Can you analyze this data?",
        },
    )
    assert resp.status_code == 201
    original_msg_id = resp.json()["id"]

    # Agent B responds proactively via callback (no auth required)
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants/{agent_b_id}/callback",
        json={
            "content": "Analysis complete. Found 3 anomalies.",
            "recipient_participant_id": agent_a_id,
            "channel_type": "message",
            "in_reply_to_id": original_msg_id,
        },
    )
    assert resp.status_code == 200, f"Callback failed: {resp.text}"
    callback_msg = resp.json()
    assert callback_msg["sender_participant_id"] == agent_b_id

    # Verify context has both messages
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/context", headers=headers
    )
    context = resp.json()
    assert len(context["entries"]) >= 2
    contents = [e["content"] for e in context["entries"]]
    assert any("analyze" in c for c in contents)
    assert any("anomalies" in c for c in contents)

    # Cleanup
    await client.delete(f"{BASE_URL}/networks/{network_id}", headers=headers)


# ── Multi-Participant Context Sharing ────────────────────────────────


@pytest.mark.asyncio
async def test_multi_participant_context(authed):
    """Three participants exchange messages; all see the full context."""
    client, token = authed
    headers = auth(token)

    # Create network with 3 participants
    resp = await client.post(
        f"{BASE_URL}/networks",
        headers=headers,
        json={"name": "Multi-Party Context Test"},
    )
    network_id = resp.json()["id"]

    participant_ids = {}
    for name in ["Persona A", "Persona B", "Persona C"]:
        resp = await client.post(
            f"{BASE_URL}/networks/{network_id}/participants",
            headers=headers,
            json={"name": name, "participant_type": "persona", "polling_enabled": True},
        )
        participant_ids[name] = resp.json()["id"]

    # A → B
    await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/send",
        headers=headers,
        json={
            "sender_participant_id": participant_ids["Persona A"],
            "recipient_participant_id": participant_ids["Persona B"],
            "content": "Hey B, should we include C in this discussion?",
        },
    )

    # B → C
    await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/send",
        headers=headers,
        json={
            "sender_participant_id": participant_ids["Persona B"],
            "recipient_participant_id": participant_ids["Persona C"],
            "content": "C, A wants to loop you in. Thoughts on the project?",
        },
    )

    # C → A (proactive via callback)
    await client.post(
        f"{BASE_URL}/networks/{network_id}/participants/{participant_ids['Persona C']}/callback",
        json={
            "content": "Thanks for including me! I have some ideas to share.",
            "recipient_participant_id": participant_ids["Persona A"],
        },
    )

    # Verify shared context has all 3 messages from all 3 senders
    resp = await client.get(
        f"{BASE_URL}/networks/{network_id}/context", headers=headers
    )
    context = resp.json()
    senders = {e["sender"] for e in context["entries"]}
    assert senders == {"Persona A", "Persona B", "Persona C"}
    assert len(context["entries"]) == 3

    # Cleanup
    await client.delete(f"{BASE_URL}/networks/{network_id}", headers=headers)


# ── A2A Agent Card ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a2a_platform_card(authed):
    """Verify the platform A2A Agent Card is served correctly."""
    client, token = authed

    resp = await client.get(f"{BASE_URL}/.well-known/agent.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "Intuno Agent Network"
    assert "capabilities" in card
    assert card["capabilities"]["networks"] is True
    assert "call" in card["capabilities"]["channels"]
    assert "message" in card["capabilities"]["channels"]
    assert "mailbox" in card["capabilities"]["channels"]
    assert len(card["skills"]) >= 4


@pytest.mark.asyncio
async def test_a2a_agent_card_for_registered_agent(authed):
    """Register an agent and verify its A2A card is generated."""
    client, token = authed
    headers = auth(token)

    agent = await register_test_agent(client, token, "A2A Card Test Agent")
    agent_id = agent["agent_id"]

    resp = await client.get(
        f"{BASE_URL}/a2a/agents/{agent_id}/agent-card", headers=headers
    )
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "A2A Card Test Agent"
    assert "skills" in card
    assert len(card["skills"]) >= 1


# ── A2A Fetch Card Preview ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_a2a_fetch_card_from_self(authed):
    """Fetch Intuno's own Agent Card via the preview endpoint."""
    client, token = authed
    headers = auth(token)

    resp = await client.get(
        f"{BASE_URL}/a2a/agents/fetch-card",
        headers=headers,
        params={"url": BASE_URL},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["card"]["name"] == "Intuno Agent Network"


# ── Network with Agent Participants ──────────────────────────────────


@pytest.mark.asyncio
async def test_network_with_agent_participants(authed):
    """Create a network where participants are linked to registered agents."""
    client, token = authed
    headers = auth(token)

    # Register two agents
    agent1 = await register_test_agent(client, token, "Network Agent Alpha")
    agent2 = await register_test_agent(client, token, "Network Agent Beta")

    # Create network
    resp = await client.post(
        f"{BASE_URL}/networks",
        headers=headers,
        json={"name": "Agent Network Test"},
    )
    network_id = resp.json()["id"]

    # Add agents as participants
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={
            "name": "Alpha",
            "agent_id": agent1["id"],
            "participant_type": "agent",
            "polling_enabled": True,
        },
    )
    assert resp.status_code == 201
    alpha_id = resp.json()["id"]
    assert resp.json()["agent_id"] == agent1["id"]

    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={
            "name": "Beta",
            "agent_id": agent2["id"],
            "participant_type": "agent",
            "polling_enabled": True,
        },
    )
    assert resp.status_code == 201
    beta_id = resp.json()["id"]

    # Verify duplicate agent is rejected
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/participants",
        headers=headers,
        json={
            "name": "Alpha Duplicate",
            "agent_id": agent1["id"],
            "polling_enabled": True,
        },
    )
    assert resp.status_code == 400

    # Exchange messages
    resp = await client.post(
        f"{BASE_URL}/networks/{network_id}/messages/send",
        headers=headers,
        json={
            "sender_participant_id": alpha_id,
            "recipient_participant_id": beta_id,
            "content": "Beta, can you process dataset X?",
        },
    )
    assert resp.status_code == 201

    # Cleanup
    await client.delete(f"{BASE_URL}/networks/{network_id}", headers=headers)
