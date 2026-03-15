from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.redis_client import close_redis, init_redis
from src.core.settings import settings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
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

# Include routers (tags defined on each router)
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

# MCP server: streamable HTTP at /mcp
app.mount("/mcp", create_mcp_app())


@app.get("/.well-known/mcp/server-card.json")
async def mcp_server_card():
    """Public metadata for MCP marketplace scanners (e.g. Smithery)."""
    return JSONResponse({
        "serverInfo": {
            "name": "Intuno Agent Network",
            "version": settings.API_VERSION,
        },
        "authentication": {
            "required": True,
            "schemes": ["apiKey"],
        },
        "tools": [
            {"name": "discover_agents", "description": "Search for AI agents by natural-language query"},
            {"name": "get_agent_details", "description": "Get full details of a specific agent including its input schema"},
            {"name": "invoke_agent", "description": "Invoke an agent with the provided input data"},
            {"name": "create_task", "description": "Create and run a multi-step task via the Intuno orchestrator"},
            {"name": "get_task_status", "description": "Check the current status and result of a previously created task"},
        ],
        "resources": [
            {"uri": "intuno://agents/trending", "description": "Trending agents by recent invocation count"},
            {"uri": "intuno://agents/new", "description": "Recently published agents (last 7 days)"},
        ],
        "prompts": [],
    })
