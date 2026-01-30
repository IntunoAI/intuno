"""Expose routes for the agents app."""

from agents.routes.agent_config import router as agent_config_router
from agents.routes.health import router as health_router

__all__ = ["agent_config_router", "health_router"]
