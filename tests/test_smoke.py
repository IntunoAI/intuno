"""Smoke tests that run in CI without a live backend.

Verifies the FastAPI app can be imported and basic endpoints respond.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_openapi_schema(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] == "Intuno"


@pytest.mark.asyncio
async def test_a2a_agent_card(client):
    response = await client.get("/.well-known/agent.json")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Intuno Agent Network"
    assert "capabilities" in data
    assert "skills" in data
    assert len(data["skills"]) == 3


@pytest.mark.asyncio
async def test_mcp_server_card(client):
    response = await client.get("/.well-known/mcp/server-card.json")
    assert response.status_code == 200
    data = response.json()
    assert "serverInfo" in data
    assert "tools" in data
