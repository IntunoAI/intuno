import logging
from contextlib import asynccontextmanager

import httpx
import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.logging_config import setup_logging
from src.core.middleware import RequestTracingMiddleware
from src.core.rate_limit import RateLimitMiddleware
from src.core.redis_client import close_redis, init_redis
from src.core.settings import settings

# Initialize structured logging early
setup_logging(
    log_level=settings.LOG_LEVEL,
    json_format=settings.ENVIRONMENT != "development",
)
from src.routes.analytics import router as analytics_router
from src.routes.auth import router as auth_router
from src.routes.brand import router as brand_router
from src.routes.dashboard import router as dashboard_router
from src.routes.broker import router as broker_router
from src.routes.conversation import router as conversation_router
from src.routes.health import router as health_router
from src.routes.integration import router as integration_router
from src.routes.invocation_log import router as invocation_log_router
from src.routes.message import router as message_router
from src.routes.registry import router as registry_router
from src.routes.task import router as task_router
from src.mcp_app import create_mcp_app

# Workflow routers (from agent-os)
from src.workflow.routes.workflows import router as workflow_router
from src.workflow.routes.executions import router as execution_router
from src.workflow.routes.webhooks import router as webhook_router

# Economy routers (from agent-economy)
from src.economy.routes.wallets import router as wallets_router
from src.economy.routes.market import router as market_router
from src.economy.routes.purchases import router as purchases_router
from src.economy.routes.ws import router as ws_router

# Workflow lifecycle helpers
from src.workflow.utils.background import BackgroundRunner
from src.workflow.utils.scheduler import WorkflowScheduler
from src.workflow.utils.event_consumer import EventConsumer
from src.workflow.exceptions import AppException as WorkflowAppException

# Ensure all models are registered with SQLAlchemy metadata
import src.models  # noqa: F401

logger = logging.getLogger(__name__)


async def _load_workflow_triggers(
    app: FastAPI,
    scheduler: WorkflowScheduler,
    event_consumer: EventConsumer,
) -> None:
    """Scan workflow definitions and register their cron/event triggers."""
    from src.database import async_session_factory
    from src.workflow.repositories.workflows import WorkflowRepository
    from src.workflow.models.dsl import WorkflowDef

    async with async_session_factory() as session:
        repo = WorkflowRepository(session)
        workflows = await repo.list(limit=1000)

    runner: BackgroundRunner = app.state.background_runner

    async def cron_callback(workflow_id):
        from src.workflow.repositories.executions import ExecutionRepository

        async with async_session_factory() as session:
            wf_repo = WorkflowRepository(session)
            wf = await wf_repo.get_by_id(workflow_id)
            if wf is None:
                return
            wf_def = WorkflowDef.model_validate(wf.definition)
            exec_repo = ExecutionRepository(session)
            execution = await exec_repo.create_execution(
                workflow_id=wf.id,
                trigger_data={"source": "cron"},
            )
            await session.commit()

        runner.submit(
            execution_id=execution.id,
            context_id=execution.context_id,
            trigger_data={"source": "cron"},
            workflow_def=wf_def,
            workflow_id=workflow_id,
        )

    async def event_callback(workflow_id, event_data):
        from src.workflow.repositories.executions import ExecutionRepository

        async with async_session_factory() as session:
            wf_repo = WorkflowRepository(session)
            wf = await wf_repo.get_by_id(workflow_id)
            if wf is None:
                return
            wf_def = WorkflowDef.model_validate(wf.definition)
            exec_repo = ExecutionRepository(session)
            execution = await exec_repo.create_execution(
                workflow_id=wf.id,
                trigger_data=event_data,
            )
            await session.commit()

        runner.submit(
            execution_id=execution.id,
            context_id=execution.context_id,
            trigger_data=event_data,
            workflow_def=wf_def,
            workflow_id=workflow_id,
        )

    event_consumer.set_callback(event_callback)

    for wf in workflows:
        try:
            wf_def = WorkflowDef.model_validate(wf.definition)
        except Exception:
            continue
        for trigger in wf_def.triggers or []:
            if trigger.type == "cron" and trigger.cron:
                scheduler.register(wf.id, trigger.cron, cron_callback)
            elif trigger.type == "event" and trigger.event:
                event_consumer.register(trigger.event, wf.id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warn if JWT secret is not configured (safe for local dev, dangerous in production)
    if not settings.JWT_SECRET_KEY:
        logger.warning(
            "JWT_SECRET_KEY is not set — authentication will not work. Set it in your .env file."
        )
    elif (
        settings.JWT_SECRET_KEY == "dev-secret-change-in-prod"
        and settings.ENVIRONMENT != "development"
    ):
        logger.warning(
            "JWT_SECRET_KEY is using the default dev value in a non-development environment. Change it immediately."
        )

    # Shared HTTP client for broker → agent invocations (connection pooling)
    app.state.http_client = httpx.AsyncClient(
        limits=httpx.Limits(
            max_keepalive_connections=settings.BROKER_HTTP_POOL_SIZE,
            max_connections=settings.BROKER_HTTP_MAX_CONNECTIONS,
        ),
        follow_redirects=False,
    )

    # Redis (shared by core, workflow, and economy)
    await init_redis()
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Workflow lifecycle
    app.state.background_runner = BackgroundRunner(app.state.redis)
    scheduler = WorkflowScheduler()
    event_consumer = EventConsumer(app.state.redis)
    app.state.scheduler = scheduler
    app.state.event_consumer = event_consumer

    await _load_workflow_triggers(app, scheduler, event_consumer)
    await scheduler.start()
    await event_consumer.start()

    yield

    # Shutdown
    await app.state.http_client.aclose()
    await event_consumer.stop()
    await scheduler.stop()
    await app.state.background_runner.shutdown()
    await app.state.redis.aclose()
    await close_redis()


app = FastAPI(
    title="Intuno",
    description="Registry and broker for AI agent discovery and collaboration",
    version=settings.API_VERSION,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request tracing middleware (X-Request-ID + timing)
app.add_middleware(RequestTracingMiddleware)

# Rate limiting middleware (Redis-backed, graceful degradation)
app.add_middleware(RateLimitMiddleware)


# Workflow exception handler
@app.exception_handler(WorkflowAppException)
async def handle_workflow_exception(_request: Request, exc: WorkflowAppException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


# ── Existing wisdom routers ──────────────────────────────────────────
app.include_router(health_router)
app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(brand_router)
app.include_router(dashboard_router)
app.include_router(integration_router)
app.include_router(registry_router)
app.include_router(broker_router)
app.include_router(conversation_router)
app.include_router(message_router)
app.include_router(invocation_log_router)
app.include_router(task_router)

# ── Workflow routers (from agent-os) ─────────────────────────────────
app.include_router(workflow_router, prefix="/workflows", tags=["Workflows"])
app.include_router(execution_router, tags=["Executions"])
app.include_router(webhook_router, tags=["Webhooks"])

# ── Economy routers (from agent-economy) ─────────────────────────────
app.include_router(wallets_router, prefix="/wallets", tags=["Wallets"])
app.include_router(market_router, prefix="/market", tags=["Market"])
app.include_router(purchases_router, prefix="/credits", tags=["Credits"])
app.include_router(ws_router, tags=["WebSocket"])

# MCP server: streamable HTTP at /mcp
app.mount("/mcp", create_mcp_app())


@app.get("/.well-known/agent.json")
async def a2a_agent_card():
    """A2A-compatible AgentCard for agent-to-agent discovery."""
    return JSONResponse(
        {
            "name": "Intuno Agent Network",
            "description": "Registry, broker, and orchestrator for AI agents",
            "url": "https://api.intuno.ai",
            "version": settings.API_VERSION,
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
            },
            "skills": [
                {
                    "id": "discover",
                    "name": "Discover Agents",
                    "description": "Semantic search for AI agents by natural-language query",
                },
                {
                    "id": "invoke",
                    "name": "Invoke Agent",
                    "description": "Execute an agent with input data through the broker",
                },
                {
                    "id": "orchestrate",
                    "name": "Orchestrate Task",
                    "description": "Multi-step task orchestration across multiple agents",
                },
            ],
            "authentication": {
                "schemes": ["apiKey", "bearer"],
            },
        }
    )


@app.get("/.well-known/mcp/server-card.json")
async def mcp_server_card():
    """Public metadata for MCP marketplace scanners (e.g. Smithery)."""
    return JSONResponse(
        {
            "serverInfo": {
                "name": "Intuno Agent Network",
                "version": settings.API_VERSION,
            },
            "authentication": {
                "required": True,
                "schemes": ["apiKey"],
            },
            "tools": [
                {
                    "name": "discover_agents",
                    "description": "Search for AI agents by natural-language query",
                },
                {
                    "name": "get_agent_details",
                    "description": "Get full details of a specific agent including its input schema",
                },
                {
                    "name": "invoke_agent",
                    "description": "Invoke an agent with the provided input data",
                },
                {
                    "name": "create_task",
                    "description": "Create and run a multi-step task via the Intuno orchestrator",
                },
                {
                    "name": "get_task_status",
                    "description": "Check the current status and result of a previously created task",
                },
            ],
            "resources": [
                {
                    "uri": "intuno://agents/trending",
                    "description": "Trending agents by recent invocation count",
                },
                {
                    "uri": "intuno://agents/new",
                    "description": "Recently published agents (last 7 days)",
                },
            ],
            "prompts": [],
        }
    )
