"""Expose all routes for easy importing."""

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

__all__ = [
    "auth_router",
    "brand_router",
    "broker_router",
    "conversation_router",
    "health_router",
    "integration_router",
    "invocation_log_router",
    "message_router",
    "registry_router",
    "task_router",
]
