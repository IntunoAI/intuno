"""MCP server mounted inside the Wisdom FastAPI app.

Exposes the Intuno Agent Network as MCP tools and resources at /mcp.
Authenticates via X-API-Key header (same as broker/task routes).
"""

import contextvars
import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.database import AsyncSessionLocal
from src.repositories.auth import AuthRepository
from src.repositories.brand import BrandRepository
from src.repositories.broker import BrokerConfigRepository
from src.repositories.conversation import ConversationRepository
from src.repositories.invocation_log import InvocationLogRepository
from src.repositories.message import MessageRepository
from src.repositories.registry import RegistryRepository
from src.repositories.task import TaskRepository
from src.schemas.broker import InvokeRequest
from src.schemas.registry import AgentSearchQuery, DiscoverQuery
from src.schemas.task import TaskCreate
from src.services.auth import AuthService
from src.services.broker import BrokerService
from src.services.registry import RegistryService
from src.services.task import TaskService
from src.utilities.embedding import EmbeddingService
from src.utilities.executor import Executor
from src.utilities.orchestrator import Orchestrator, OrchestratorContext
from src.core.settings import settings

logger = logging.getLogger(__name__)

# Auth context passed from middleware to tool handlers
_current_user_id: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "mcp_user_id", default=None
)
_current_integration_id: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "mcp_integration_id", default=None
)

mcp_server = FastMCP(
    "Intuno Agent Network",
    instructions=(
        "Discover, invoke, and orchestrate AI agents on the Intuno Agent Network. "
        "Use these tools to find agents by description, execute agent functions, "
        "and run multi-step tasks."
    ),
    stateless_http=True,
)


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------


class ApiKeyAuthMiddleware:
    """ASGI middleware that validates X-API-Key before forwarding to the MCP app."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        api_key = request.headers.get("x-api-key") or _parse_bearer(
            request.headers.get("authorization")
        )

        if not api_key:
            response = JSONResponse(
                {"error": "X-API-Key or Authorization header required"}, status_code=401
            )
            await response(scope, receive, send)
            return

        async with AsyncSessionLocal() as session:
            auth_repo = AuthRepository(session)
            auth_service = AuthService(auth_repo)
            ctx = await auth_service.verify_api_key_and_get_context(api_key)

        if not ctx:
            response = JSONResponse(
                {"error": "Invalid or expired API key"}, status_code=401
            )
            await response(scope, receive, send)
            return

        user, integration_id = ctx
        token_user = _current_user_id.set(user.id)
        token_integration = _current_integration_id.set(integration_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_user_id.reset(token_user)
            _current_integration_id.reset(token_integration)


def _parse_bearer(header: Optional[str]) -> Optional[str]:
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


# ---------------------------------------------------------------------------
# Service factory (follows run_task_background pattern from services/task.py)
# ---------------------------------------------------------------------------


class _ServiceContext:
    """Creates service instances for a single MCP tool call with a fresh DB session."""

    def __init__(self, session):
        self.session = session
        registry_repo = RegistryRepository(session)
        invocation_log_repo = InvocationLogRepository(session)
        brand_repo = BrandRepository(session)
        broker_config_repo = BrokerConfigRepository(session)
        conversation_repo = ConversationRepository(session)
        message_repo = MessageRepository(session)
        task_repo = TaskRepository(session)
        embedding_service = EmbeddingService()

        self.registry = RegistryService(
            registry_repository=registry_repo,
            invocation_log_repository=invocation_log_repo,
            embedding_service=embedding_service,
            brand_repository=brand_repo,
        )
        self.broker = BrokerService(
            invocation_log_repository=invocation_log_repo,
            broker_config_repository=broker_config_repo,
            registry_repository=registry_repo,
            conversation_repository=conversation_repo,
            message_repository=message_repo,
        )
        self.task = TaskService(
            task_repository=task_repo,
            conversation_repository=conversation_repo,
            message_repository=message_repo,
            registry_service=self.registry,
            broker_service=self.broker,
            embedding_service=embedding_service,
            broker_config_repository=broker_config_repo,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_summary(agent) -> Dict[str, Any]:
    """Compact JSON-serializable summary of an agent ORM object."""
    summary: Dict[str, Any] = {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "endpoint": agent.invoke_endpoint,
        "auth_type": agent.auth_type,
    }
    if agent.input_schema:
        summary["input_schema"] = agent.input_schema
    if agent.tags:
        summary["tags"] = agent.tags
    if getattr(agent, "category", None):
        summary["category"] = agent.category
    return summary


def _agent_list_summary(agents) -> List[Dict[str, Any]]:
    return [_agent_summary(a) for a in agents]


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp_server.tool()
async def discover_agents(query: str, limit: int = 5) -> str:
    """Search for AI agents by describing what you need in natural language.

    Returns a list of matching agents.
    Use this to find agents before invoking them.

    Args:
        query: Natural language description of the desired agent
               (e.g. "summarize text", "translate to Spanish", "analyze sentiment").
        limit: Maximum number of agents to return (1-50, default 5).
    """
    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        discover_query = DiscoverQuery(
            query=query, limit=min(max(limit, 1), 50)
        )
        results = await svc.registry.semantic_discover(discover_query)
        agents = [agent for agent, _ in results]
        return json.dumps(_agent_list_summary(agents), indent=2, default=str)


@mcp_server.tool()
async def get_agent_details(agent_id: str) -> str:
    """Get full details of a specific agent including its input schema.

    Use this after discovering agents to inspect a particular agent's
    input/output schemas before invoking it.

    Args:
        agent_id: The agent ID (e.g. "agent:namespace:name:version").
    """
    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        agent = await svc.registry.get_agent(agent_id)
        if not agent:
            return json.dumps({"error": f"Agent '{agent_id}' not found"})
        return json.dumps(_agent_summary(agent), indent=2, default=str)


@mcp_server.tool()
async def invoke_agent(
    agent_id: str,
    input_data: dict,
) -> str:
    """Invoke an agent with the provided input data.

    Before calling this, use discover_agents or get_agent_details to find
    the correct agent_id and required input schema.

    Args:
        agent_id: The agent ID to invoke.
        input_data: Input data matching the agent's input_schema.
    """
    user_id = _current_user_id.get()
    integration_id = _current_integration_id.get()
    if not user_id:
        return json.dumps({"error": "Not authenticated"})

    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        invoke_request = InvokeRequest(
            agent_id=agent_id,
            input=input_data,
        )
        result = await svc.broker.invoke_agent(
            invoke_request,
            caller_user_id=user_id,
            integration_id=integration_id,
        )
        return json.dumps(
            {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "latency_ms": result.latency_ms,
            },
            indent=2,
            default=str,
        )


@mcp_server.tool()
async def create_task(
    goal: str,
    input_data: Optional[dict] = None,
) -> str:
    """Create and run a multi-step task via the Intuno orchestrator.

    The orchestrator will automatically discover relevant agents, plan the
    execution steps, and invoke them in sequence to achieve the goal.

    Args:
        goal: Natural language description of what you want to accomplish.
        input_data: Optional input data for the task.
    """
    user_id = _current_user_id.get()
    integration_id = _current_integration_id.get()
    if not user_id:
        return json.dumps({"error": "Not authenticated"})

    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        data = TaskCreate(goal=goal, input=input_data or {})
        task, _ = await svc.task.create(
            user_id=user_id,
            integration_id=integration_id,
            data=data,
        )
        return json.dumps(
            {
                "task_id": str(task.id),
                "status": task.status,
                "goal": task.goal,
                "result": task.result,
                "error_message": task.error_message,
                "steps": task.steps,
            },
            indent=2,
            default=str,
        )


@mcp_server.tool()
async def get_task_status(task_id: str) -> str:
    """Check the current status and result of a previously created task.

    Use this to poll async tasks or to retrieve the final result of a completed task.

    Args:
        task_id: The task ID returned by create_task.
    """
    user_id = _current_user_id.get()
    if not user_id:
        return json.dumps({"error": "Not authenticated"})

    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        task = await svc.task.get(UUID(task_id), user_id)
        if not task:
            return json.dumps({"error": "Task not found"})
        return json.dumps(
            {
                "task_id": str(task.id),
                "status": task.status,
                "goal": task.goal,
                "result": task.result,
                "error_message": task.error_message,
                "steps": task.steps,
                "created_at": str(task.created_at),
                "updated_at": str(task.updated_at),
            },
            indent=2,
            default=str,
        )


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------


@mcp_server.resource("intuno://agents/trending")
async def trending_agents() -> str:
    """Trending agents on the Intuno network, ordered by recent invocation count."""
    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        results = await svc.registry.get_trending_agents(window_days=7, limit=20)
        agents = [agent for agent, _ in results]
        return json.dumps(_agent_list_summary(agents), indent=2, default=str)


@mcp_server.resource("intuno://agents/new")
async def new_agents() -> str:
    """Recently published agents on the Intuno network (last 7 days)."""
    async with AsyncSessionLocal() as session:
        svc = _ServiceContext(session)
        query = AgentSearchQuery(sort="created_at", order="desc", days=7, limit=20)
        agents = await svc.registry.list_agents(query)
        return json.dumps(_agent_list_summary(agents), indent=2, default=str)


# ---------------------------------------------------------------------------
# ASGI app (mounted in main.py)
# ---------------------------------------------------------------------------


def create_mcp_app() -> ASGIApp:
    """Build the MCP ASGI application with auth middleware."""
    app = mcp_server.streamable_http_app()
    return ApiKeyAuthMiddleware(app)
