"""A2A-compatible API endpoints.

Provides endpoints that follow the A2A protocol specification, allowing
A2A-compatible agents to interact with Intuno networks.

See: https://google.github.io/A2A/specification/
"""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.core.auth import get_current_user
from src.models.auth import User
from src.network.a2a.agent_card import build_agent_card, build_platform_card
from src.network.a2a.protocol import (
    a2a_task_to_intuno_message,
    build_a2a_json_rpc_error,
    build_a2a_json_rpc_response,
    intuno_message_to_a2a_task,
)
from src.repositories.registry import RegistryRepository

router = APIRouter(prefix="/a2a", tags=["A2A"])


# ── Agent Card endpoints ─────────────────────────────────────────────


@router.get("/agent-card")
async def get_platform_agent_card() -> JSONResponse:
    """Serve the platform-level A2A Agent Card."""
    return JSONResponse(build_platform_card())


@router.get("/agents/{agent_id}/agent-card")
async def get_agent_card(
    agent_id: str,
    registry: RegistryRepository = Depends(),
) -> JSONResponse:
    """Serve an A2A Agent Card for a specific registered agent."""
    agent = await registry.get_agent_by_agent_id(agent_id)
    if not agent:
        return JSONResponse(
            build_a2a_json_rpc_error(-32602, f"Agent '{agent_id}' not found"),
            status_code=404,
        )
    return JSONResponse(build_agent_card(agent))


# ── A2A Task endpoints (JSON-RPC style) ──────────────────────────────


class A2ATaskSendRequest(BaseModel):
    """A2A tasks/send request body."""

    jsonrpc: str = "2.0"
    id: Optional[str | int] = None
    method: str = "tasks/send"
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/tasks/send")
async def a2a_task_send(
    data: A2ATaskSendRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """A2A-compatible task send endpoint.

    Receives an A2A task, translates it to an Intuno network message,
    processes it, and returns the result in A2A format.
    """
    from src.network.services.channels import ChannelService
    from src.network.repositories.networks import NetworkRepository
    from src.network.utils.context_manager import NetworkContextManager
    from src.database import get_redis

    params = data.params
    task_data = params.get("task", {})
    network_id = params.get("network_id")
    sender_participant_id = params.get("sender_participant_id")
    recipient_participant_id = params.get("recipient_participant_id")

    if not network_id or not sender_participant_id:
        return JSONResponse(
            build_a2a_json_rpc_error(
                -32602,
                "Missing required params: network_id, sender_participant_id",
                data.id,
            ),
            status_code=400,
        )

    # Convert A2A task to Intuno message format
    intuno_msg = a2a_task_to_intuno_message(task_data)

    # Process through the channel service
    try:
        redis = request.app.state.redis
        repo = NetworkRepository(
            session=(await request.app.state.db_session_factory()).__aenter__()
        )
        ctx_manager = NetworkContextManager(redis)
        channel_service = ChannelService(repo=repo, context_manager=ctx_manager)
        channel_service.set_http_client(request.app.state.http_client)

        channel_type = intuno_msg.get("channel_type", "message")

        if channel_type == "call" and recipient_participant_id:
            result = await channel_service.call(
                network_id=UUID(network_id),
                sender_participant_id=UUID(sender_participant_id),
                recipient_participant_id=UUID(recipient_participant_id),
                content=intuno_msg["content"],
                metadata=intuno_msg.get("metadata"),
            )
            # Convert result back to A2A task format
            a2a_result = {
                "id": result.get("message_id"),
                "status": {"state": "completed"},
                "artifacts": [
                    {
                        "parts": [
                            {"type": "text", "text": str(result.get("response", ""))}
                        ]
                    }
                ],
            }
        else:
            message = await channel_service.send_message(
                network_id=UUID(network_id),
                sender_participant_id=UUID(sender_participant_id),
                recipient_participant_id=UUID(recipient_participant_id),
                content=intuno_msg["content"],
                metadata=intuno_msg.get("metadata"),
            )
            a2a_result = intuno_message_to_a2a_task(
                {
                    "id": message.id,
                    "status": message.status,
                    "content": message.content,
                    "network_id": message.network_id,
                    "channel_type": message.channel_type,
                    "created_at": message.created_at,
                },
            )

        return JSONResponse(build_a2a_json_rpc_response(a2a_result, data.id))

    except Exception as exc:
        return JSONResponse(
            build_a2a_json_rpc_error(-32603, str(exc), data.id),
            status_code=500,
        )


# ── A2A Agent Discovery & Import ─────────────────────────────────────


@router.get("/agents")
async def list_a2a_agents(
    registry: RegistryRepository = Depends(),
) -> JSONResponse:
    """List all agents with A2A support enabled."""
    agents = await registry.list_agents(limit=100)
    cards = []
    for agent in agents:
        if getattr(agent, "is_active", False):
            cards.append(build_agent_card(agent))
    return JSONResponse({"agents": cards})


class A2AImportRequest(BaseModel):
    """Import an external A2A agent by its base URL."""

    url: str = Field(..., description="Base URL of the A2A-compatible agent")


class A2ABatchImportRequest(BaseModel):
    """Import multiple external A2A agents."""

    urls: list[str] = Field(..., description="List of A2A agent base URLs")


@router.post("/agents/import")
async def import_a2a_agent(
    data: A2AImportRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Import an external A2A agent as a first-class Intuno agent.

    Fetches the Agent Card from the given URL, creates a registry entry,
    generates embeddings, and indexes in Qdrant. The agent becomes fully
    discoverable and invocable — just like any natively registered agent.
    """
    discovery_service = await _get_discovery_service(request)
    discovery_service.set_http_client(request.app.state.http_client)

    try:
        agent = await discovery_service.import_agent(data.url, current_user.id)
        return JSONResponse(
            {
                "success": True,
                "agent_id": agent.agent_id,
                "name": agent.name,
                "description": agent.description,
                "invoke_endpoint": agent.invoke_endpoint,
                "tags": agent.tags,
            },
            status_code=201,
        )
    except ValueError as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)},
            status_code=400,
        )


@router.post("/agents/import/batch")
async def import_a2a_agents_batch(
    data: A2ABatchImportRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Import multiple external A2A agents in one request."""
    discovery_service = await _get_discovery_service(request)
    discovery_service.set_http_client(request.app.state.http_client)

    results = await discovery_service.import_multiple(data.urls, current_user.id)
    return JSONResponse({"results": results})


@router.post("/agents/{agent_id}/refresh")
async def refresh_a2a_agent(
    agent_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Re-fetch the Agent Card and update the registry entry."""
    discovery_service = await _get_discovery_service(request)
    discovery_service.set_http_client(request.app.state.http_client)

    agent = await discovery_service.registry_repository.get_agent_by_agent_id(agent_id)
    if not agent:
        return JSONResponse(
            build_a2a_json_rpc_error(-32602, f"Agent '{agent_id}' not found"),
            status_code=404,
        )

    try:
        updated = await discovery_service.refresh_agent(agent.id, current_user.id)
        return JSONResponse(
            {
                "success": True,
                "agent_id": updated.agent_id,
                "name": updated.name,
            }
        )
    except ValueError as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)},
            status_code=400,
        )


@router.get("/agents/fetch-card")
async def fetch_agent_card_preview(
    url: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Preview an A2A Agent Card without importing it."""
    discovery_service = await _get_discovery_service(request)
    discovery_service.set_http_client(request.app.state.http_client)

    card = await discovery_service.fetch_agent_card(url)
    if card is None:
        return JSONResponse(
            {"success": False, "error": f"Could not fetch Agent Card from {url}"},
            status_code=404,
        )
    return JSONResponse({"success": True, "card": card})


async def _get_discovery_service(request: Request):
    """Helper to build a discovery service from request context."""
    from src.network.a2a.discovery import A2ADiscoveryService
    from src.database import AsyncSessionLocal
    from src.utilities.embedding import EmbeddingService

    session = AsyncSessionLocal()
    return A2ADiscoveryService(
        registry_repository=RegistryRepository(session=session),
        embedding_service=EmbeddingService(),
    )
