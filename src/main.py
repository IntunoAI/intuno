from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.settings import settings
from src.routes.auth import router as auth_router
from src.routes.brand import router as brand_router
from src.routes.broker import router as broker_router
from src.routes.conversation import router as conversation_router
from src.routes.health import router as health_router
from src.routes.integration import router as integration_router
from src.routes.invocation_log import router as invocation_log_router
from src.routes.message import router as message_router
from src.routes.registry import router as registry_router
from src.routes.task import router as task_router
from src.mcp_app import create_mcp_app

app = FastAPI(
    title="Intuno",
    description="Registry and broker for AI agent discovery and collaboration",
    version=settings.API_VERSION,
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
app.include_router(auth_router)
app.include_router(brand_router)
app.include_router(integration_router)
app.include_router(registry_router)
app.include_router(broker_router)
app.include_router(conversation_router)
app.include_router(message_router)
app.include_router(invocation_log_router)
app.include_router(task_router)

# MCP server: streamable HTTP at /mcp
app.mount("/mcp", create_mcp_app())
