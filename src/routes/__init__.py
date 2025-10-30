"""Expose all routes for easy importing."""

from src.routes.auth import router as auth_router
from src.routes.broker import router as broker_router
from src.routes.health import router as health_router
from src.routes.registry import router as registry_router

__all__ = [
    "health_router",
    "auth_router",
    "registry_router",
    "broker_router",
]
