"""Registry routes for agent management."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import get_current_user
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
    registry_service: RegistryService = Depends(),
):
    """Register a new agent.
    :param agent_data: AgentCreate
    :param current_user: User
    :param registry_service: RegistryService
    :return: AgentResponse
    """
    
    try:
        agent = await registry_service.register_agent(agent_data.manifest, current_user.id)
        
        # Convert capabilities to response format
        capabilities = []
        for cap in agent.capabilities:
            capabilities.append({
                "id": cap.capability_id,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "auth_type": {"type": cap.auth_type},
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
    _: User = Depends(get_current_user),
    tags: List[str] = Query(default=None),
    capability: str = Query(default=None),
    search: str = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    registry_service: RegistryService = Depends(),
):
    """List and search agents.
    :param _: User
    :param tags: List[str]
    :param capability: str
    :param search: str
    :param limit: int
    :param offset: int
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    
    query = AgentSearchQuery(
        tags=tags,
        capability=capability,
        search=search,
        limit=limit,
        offset=offset,
    )
    
    agents = await registry_service.list_agents(query)
    
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
            capabilities=[
                {
                    "id": cap.capability_id,
                    "input_schema": cap.input_schema,
                    "output_schema": cap.output_schema,
                    "auth_type": {"type": cap.auth_type},
                }
                for cap in agent.capabilities
            ],
        )
        for agent in agents
    ]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    registry_service: RegistryService = Depends(),
):
    """Get agent details by agent_id.
    :param agent_id: str
    :param registry_service: RegistryService
    :return: AgentResponse
    """
    
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
    registry_service: RegistryService = Depends(),
):
    """Update an agent (owner only).
    :param agent_uuid: UUID
    :param agent_data: AgentUpdate
    :param current_user: User
    :param registry_service: RegistryService
    :return: AgentResponse
    """
    
    try:
        agent = await registry_service.update_agent(agent_uuid, agent_data.manifest, current_user.id)
        
        # Convert capabilities to response format
        capabilities = []
        for cap in agent.capabilities:
            capabilities.append({
                "id": cap.capability_id,
                "input_schema": cap.input_schema,
                "output_schema": cap.output_schema,
                "auth_type": {"type": cap.auth_type},
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
    registry_service: RegistryService = Depends(),
):
    """Delete an agent (owner only).
    :param agent_uuid: UUID
    :param current_user: User
    :param registry_service: RegistryService
    :return: None
    """
    
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
async def semantic_discover(
    query: str = Query(..., description="Natural language query for semantic search"),
    limit: int = Query(default=10, ge=1, le=50),
    registry_service: RegistryService = Depends(),
):
    """
    Semantic discovery of agents using vector similarity.
    :param query: str
    :param limit: int
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    
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
async def get_agents_by_user_id(
    current_user: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """
    Get current user's agents.
    :param current_user: User
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    
    agents = await registry_service.get_agents_by_user_id(current_user.id)
    
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
