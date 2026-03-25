import uuid

from fastapi import APIRouter, Depends, Query

from src.economy.schemas.agent import (
    AgentCreate,
    AgentListResponse,
    AgentResponse,
    AgentUpdate,
)
from src.economy.services.agents import AgentService

router = APIRouter()


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    payload: AgentCreate,
    agent_service: AgentService = Depends(),
) -> AgentResponse:
    """Register a new agent in the economy."""
    return await agent_service.create_agent(payload)


@router.get("", response_model=list[AgentListResponse])
async def list_agents(
    agent_service: AgentService = Depends(),
    is_active: bool | None = Query(None),
    capability: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AgentListResponse]:
    """List agents with optional filters."""
    return await agent_service.list_agents(
        is_active=is_active,
        capability=capability,
        limit=limit,
        offset=offset,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    agent_service: AgentService = Depends(),
) -> AgentResponse:
    """Retrieve a single agent by ID."""
    return await agent_service.get_agent(agent_id)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    agent_service: AgentService = Depends(),
) -> AgentResponse:
    """Update an existing agent."""
    return await agent_service.update_agent(agent_id, payload)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    agent_service: AgentService = Depends(),
) -> None:
    """Remove an agent from the economy."""
    await agent_service.delete_agent(agent_id)
