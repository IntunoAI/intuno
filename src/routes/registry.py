"""Registry routes for agent management."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user
from src.database import get_db
from src.models.auth import User
from src.schemas.registry import (
    AgentCreate,
    AgentListResponse,
    AgentResponse,
    AgentSearchQuery,
    AgentUpdate,
    DiscoverQuery,
)
from src.services.registry import RegistryService

router = APIRouter(prefix="/registry", tags=["Registry"])


@router.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Register a new agent."""
    registry_service = RegistryService(db)
    
    try:
        agent = await registry_service.register_agent(agent_data.manifest, current_user.id)
        
        # Convert capabilities to response format
        capabilities = []
        for cap in agent.capabilities:
            capabilities.append({
                "id": cap.capability_id,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "auth_type": cap.auth_type,
            })
        
        # Convert requirements to response format
        requirements = []
        for req in agent.requirements:
            requirements.append({"capability": req.required_capability})
        
        return AgentResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            invoke_endpoint=agent.invoke_endpoint,
            manifest_json=agent.manifest_json,
            tags=agent.tags,
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            capabilities=capabilities,
            requirements=requirements,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/agents", response_model=List[AgentListResponse])
async def list_agents(
    tags: List[str] = Query(default=None),
    capability: str = Query(default=None),
    search: str = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List and search agents."""
    registry_service = RegistryService(db)
    
    query = AgentSearchQuery(
        tags=tags,
        capability=capability,
        search=search,
        limit=limit,
        offset=offset,
    )
    
    agents = await registry_service.search_agents(query)
    
    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
        )
        for agent in agents
    ]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get agent details by agent_id."""
    registry_service = RegistryService(db)
    
    agent = await registry_service.get_agent(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )
    
    # Convert capabilities to response format
    capabilities = []
    for cap in agent.capabilities:
        capabilities.append({
            "id": cap.capability_id,
            "input_schema": cap.input_schema,
            "output_schema": cap.output_schema,
            "auth_type": cap.auth_type,
        })
    
    # Convert requirements to response format
    requirements = []
    for req in agent.requirements:
        requirements.append({"capability": req.required_capability})
    
    return AgentResponse(
        id=agent.id,
        agent_id=agent.agent_id,
        name=agent.name,
        description=agent.description,
        version=agent.version,
        invoke_endpoint=agent.invoke_endpoint,
        manifest_json=agent.manifest_json,
        tags=agent.tags,
        trust_verification=agent.trust_verification,
        is_active=agent.is_active,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        capabilities=capabilities,
        requirements=requirements,
    )


@router.put("/agents/{agent_uuid}", response_model=AgentResponse)
async def update_agent(
    agent_uuid: UUID,
    agent_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an agent (owner only)."""
    registry_service = RegistryService(db)
    
    try:
        agent = await registry_service.update_agent(agent_uuid, agent_data.manifest, current_user.id)
        
        # Convert capabilities to response format
        capabilities = []
        for cap in agent.capabilities:
            capabilities.append({
                "id": cap.capability_id,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "auth_type": cap.auth_type,
            })
        
        # Convert requirements to response format
        requirements = []
        for req in agent.requirements:
            requirements.append({"capability": req.required_capability})
        
        return AgentResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            invoke_endpoint=agent.invoke_endpoint,
            manifest_json=agent.manifest_json,
            tags=agent.tags,
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            capabilities=capabilities,
            requirements=requirements,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/agents/{agent_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_uuid: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent (owner only)."""
    registry_service = RegistryService(db)
    
    try:
        success = await registry_service.delete_agent(agent_uuid, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found",
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get("/discover", response_model=List[AgentListResponse])
async def discover_agents(
    query: str = Query(..., description="Natural language query for semantic search"),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Semantic discovery of agents."""
    registry_service = RegistryService(db)
    
    discover_query = DiscoverQuery(query=query, limit=limit)
    agents = await registry_service.semantic_discover(discover_query)
    
    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
        )
        for agent in agents
    ]


@router.get("/my-agents", response_model=List[AgentListResponse])
async def get_my_agents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's agents."""
    registry_service = RegistryService(db)
    
    agents = await registry_service.get_user_agents(current_user.id)
    
    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
        )
        for agent in agents
    ]
