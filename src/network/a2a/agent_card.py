"""A2A Agent Card generation and serving.

Generates JSON-LD Agent Cards from the Intuno agent registry for agents
that opt into A2A interoperability.  Cards are served at
``GET /.well-known/agent.json`` (platform-level) and per-agent endpoints.
"""

from typing import Any, Optional
from uuid import UUID

from src.core.settings import settings


def build_agent_card(
    agent: Any,
    capabilities: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build an A2A Agent Card from an Intuno agent registry entry.

    See: https://google.github.io/A2A/specification/
    """
    card: dict[str, Any] = {
        "name": agent.name,
        "description": agent.description,
        "url": f"{settings.BASE_URL}/a2a/agents/{agent.agent_id}",
        "version": getattr(agent, "version", "1.0.0"),
        "capabilities": {
            "streaming": getattr(agent, "supports_streaming", False),
            "pushNotifications": True,  # via network callback mechanism
            **(capabilities or {}),
        },
        "skills": _build_skills(agent),
        "authentication": _build_auth(agent),
    }

    # Add input schema if available
    if agent.input_schema:
        card["defaultInputModes"] = ["application/json"]
        card["defaultOutputModes"] = ["application/json"]

    return card


def build_platform_card() -> dict[str, Any]:
    """Build the platform-level A2A Agent Card for Intuno itself."""
    return {
        "name": "Intuno Agent Network",
        "description": (
            "Registry, broker, and orchestrator for AI agents. "
            "Supports multi-directional agent communication with calls, "
            "messages, and mailboxes."
        ),
        "url": settings.BASE_URL,
        "version": settings.API_VERSION,
        "capabilities": {
            "streaming": True,
            "pushNotifications": True,
            "networks": True,
            "topologies": ["mesh", "star", "ring", "custom"],
            "channels": ["call", "message", "mailbox"],
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
            {
                "id": "network",
                "name": "Communication Network",
                "description": (
                    "Create multi-directional communication networks between agents "
                    "with calls, messages, and mailboxes"
                ),
            },
        ],
        "authentication": {
            "schemes": ["apiKey", "bearer"],
        },
    }


def _build_skills(agent: Any) -> list[dict[str, str]]:
    """Extract skills from agent metadata."""
    skills = []

    # If agent has a2a_capabilities, use those
    a2a_caps = getattr(agent, "a2a_capabilities", None)
    if a2a_caps and isinstance(a2a_caps, list):
        for cap in a2a_caps:
            if isinstance(cap, dict):
                skills.append(cap)
            elif isinstance(cap, str):
                skills.append({"id": cap, "name": cap, "description": cap})
        return skills

    # Default: generate a single skill from agent description
    skills.append({
        "id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
    })
    return skills


def _build_auth(agent: Any) -> dict[str, Any]:
    """Build authentication section from agent auth_type."""
    auth_type = getattr(agent, "auth_type", "public") or "public"

    if auth_type == "public":
        return {"schemes": []}
    elif auth_type == "api_key":
        return {"schemes": ["apiKey"]}
    elif auth_type == "bearer_token":
        return {"schemes": ["bearer"]}

    return {"schemes": [auth_type]}
