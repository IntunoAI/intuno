"""Tests for the Wisdom SDK client."""

import pytest
import respx
from httpx import Response
from src.wisdom_sdk import WisdomClient
from src.wisdom_sdk.exceptions import (
    APIKeyMissingError,
    AuthenticationError,
    InvocationError,
    WisdomError,
)

# --- Fixtures ---

BASE_URL = WisdomClient.DEFAULT_BASE_URL
API_KEY = "test-api-key"


@pytest.fixture
def client():
    return WisdomClient(api_key=API_KEY)


# --- Test Cases ---


def test_init_requires_api_key():
    """Test that initializing the client without an API key raises an error."""
    with pytest.raises(APIKeyMissingError):
        WisdomClient(api_key="")


@pytest.mark.asyncio
@respx.mock
async def test_discover_success(client: WisdomClient):
    """Test successful agent discovery."""
    mock_response = [
        {
            "id": "uuid-1",
            "agentId": "agent-1",
            "name": "Test Agent 1",
            "description": "A test agent",
            "version": "1.0",
            "tags": ["test"],
            "isActive": True,
            "capabilities": [
                {
                    "id": "cap-1",
                    "name": "Test Capability",
                    "description": "A test capability",
                    "inputSchema": {},
                    "outputSchema": {},
                }
            ],
        }
    ]
    respx.get(f"{BASE_URL}/registry/discover?query=test&limit=10").mock(
        return_value=Response(200, json=mock_response)
    )

    async with client as c:
        agents = await c.discover(query="test")

    assert len(agents) == 1
    agent = agents[0]
    assert agent.agent_id == "agent-1"
    assert agent.name == "Test Agent 1"
    assert len(agent.capabilities) == 1
    assert agent.capabilities[0].id == "cap-1"


@pytest.mark.asyncio
@respx.mock
async def test_discover_auth_error(client: WisdomClient):
    """Test that a 401 status on discover raises AuthenticationError."""
    respx.get(f"{BASE_URL}/registry/discover?query=test&limit=10").mock(
        return_value=Response(401, json={"detail": "Invalid API key"})
    )

    with pytest.raises(AuthenticationError):
        async with client as c:
            await c.discover(query="test")


@pytest.mark.asyncio
@respx.mock
async def test_invoke_success(client: WisdomClient):
    """Test successful agent invocation."""
    mock_response = {
        "success": True,
        "data": {"result": "ok"},
        "error": None,
        "latencyMs": 100,
        "statusCode": 200,
    }
    respx.post(f"{BASE_URL}/broker/invoke").mock(
        return_value=Response(200, json=mock_response)
    )

    async with client as c:
        result = await c.invoke(
            agent_id="agent-1",
            capability_id="cap-1",
            input_data={"test": "data"},
        )

    assert result.success is True
    assert result.data == {"result": "ok"}
    assert result.error is None
    assert result.status_code == 200


@pytest.mark.asyncio
@respx.mock
async def test_invoke_broker_failure_raises_invocation_error(client: WisdomClient):
    """Test that a failed but valid broker response raises InvocationError."""
    mock_response = {
        "success": False,
        "data": None,
        "error": "Agent not found",
        "latencyMs": 20,
        "statusCode": 404,
    }
    # The broker successfully handled the request and is reporting a failure,
    # so the HTTP status code is 200.
    respx.post(f"{BASE_URL}/broker/invoke").mock(
        return_value=Response(200, json=mock_response)
    )

    with pytest.raises(InvocationError, match="Invocation failed: Agent not found"):
        async with client as c:
            await c.invoke(
                agent_id="non-existent-agent",
                capability_id="cap-1",
                input_data={},
            )


@pytest.mark.asyncio
@respx.mock
async def test_invoke_http_error_raises_wisdom_error(client: WisdomClient):
    """Test that a generic HTTP error on invoke raises WisdomError."""
    respx.post(f"{BASE_URL}/broker/invoke").mock(
        return_value=Response(500, text="Internal Server Error")
    )

    with pytest.raises(WisdomError, match="API request failed: Internal Server Error"):
        async with client as c:
            await c.invoke(
                agent_id="agent-1",
                capability_id="cap-1",
                input_data={},
            )


@pytest.mark.asyncio
@respx.mock
async def test_invoke_auth_error(client: WisdomClient):
    """Test that a 401 status on invoke raises AuthenticationError."""
    respx.post(f"{BASE_URL}/broker/invoke").mock(return_value=Response(401))

    with pytest.raises(AuthenticationError):
        async with client as c:
            await c.invoke(
                agent_id="agent-1",
                capability_id="cap-1",
                input_data={},
            )
