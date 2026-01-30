"""Registry routes for agent management. Response building in routes via Pydantic/schema helpers.

Endpoints tagged "Public" (GET /agents/{agent_id}, GET /agents/{agent_id}/ratings) require
no authentication and are intended for showcasing agents and reviews in the frontend.
They return only public data (no owner/brand PII).
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import get_current_user
from src.exceptions import BadRequestException, ForbiddenException, NotFoundException
from src.models.auth import User
from src.schemas.registry import (
    AgentCreate,
    AgentListResponse,
    AgentResponse,
    AgentSearchQuery,
    AgentUpdate,
    CapabilitySchema,
    DiscoverQuery,
    RateRequest,
    RatingResponse,
    requirements_from_orm,
)
from src.services.registry import RegistryService

router = APIRouter(prefix="/registry", tags=["Registry"])


@router.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_data: AgentCreate,
    current_user: User = Depends(get_current_user),
    enhance_manifest: bool = Query(default=True, description="Whether to enhance manifest text with LLM"),
    registry_service: RegistryService = Depends(),
):
    """
    Register a new agent.
    :param agent_data: AgentCreate
    :param current_user: User
    :param enhance_manifest: bool - Whether to enhance manifest text with LLM
    :param registry_service: RegistryService
    :return: AgentResponse
    """
    
    try:
        agent = await registry_service.register_agent(
            agent_data.manifest,
            current_user.id,
            enhance_manifest=enhance_manifest,
            brand_id=agent_data.brand_id,
        )
        
        return AgentResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            invoke_endpoint=agent.invoke_endpoint,
            manifest_json=agent.manifest_json,
            tags=agent.tags,
            category=getattr(agent, "category", None),
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
            capabilities=[CapabilitySchema.from_capability(cap) for cap in agent.capabilities],
            requirements=requirements_from_orm(agent.requirements),
            rating_avg=None,
            rating_count=0,
            quality_success_rate=None,
            quality_avg_latency_ms=None,
            quality_invocation_count=0,
        )
    except ValueError as e:
        raise BadRequestException(str(e))


@router.get("/agents", response_model=List[AgentListResponse])
async def list_agents(
    _: User = Depends(get_current_user),
    tags: List[str] = Query(default=None),
    capability: str = Query(default=None),
    search: str = Query(default=None),
    category: Optional[str] = Query(default=None, description="Filter by category (when set on agent)"),
    sort: str = Query(default="created_at", description="Sort field: created_at, updated_at, name"),
    order: str = Query(default="desc", description="Sort order: asc, desc"),
    days: Optional[int] = Query(default=None, ge=1, le=365, description="Only agents created in the last N days"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    registry_service: RegistryService = Depends(),
):
    """List and search agents with optional sort, order, category, and days filter.
    :param _: User
    :param tags: List[str]
    :param capability: str
    :param search: str
    :param category: Optional[str]
    :param sort: str
    :param order: str
    :param days: Optional[int]
    :param limit: int
    :param offset: int
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    query = AgentSearchQuery(
        tags=tags,
        capability=capability,
        search=search,
        category=category,
        sort=sort,
        order=order,
        days=days,
        limit=limit,
        offset=offset,
    )

    agents = await registry_service.list_agents(query)
    agent_ids = [a.id for a in agents]
    rating_aggregates = await registry_service.get_rating_aggregates_bulk(agent_ids)
    quality_metrics = await registry_service.get_agent_quality_metrics_bulk(agent_ids)

    def _rating(agent_id):
        avg, count = rating_aggregates.get(agent_id, (None, 0))
        return (round(avg, 2) if avg is not None else None, count)

    def _quality(agent_id):
        sr, avg_lat, count = quality_metrics.get(agent_id, (None, None, 0))
        return (
            round(sr, 2) if sr is not None else None,
            round(avg_lat, 2) if avg_lat is not None else None,
            count,
        )

    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            category=getattr(agent, "category", None),
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            capabilities=[CapabilitySchema.from_capability(cap) for cap in agent.capabilities],
            rating_avg=_rating(agent.id)[0],
            rating_count=_rating(agent.id)[1],
            quality_success_rate=_quality(agent.id)[0],
            quality_avg_latency_ms=_quality(agent.id)[1],
            quality_invocation_count=_quality(agent.id)[2],
        )
        for agent in agents
    ]


@router.get("/agents/new", response_model=List[AgentListResponse])
async def list_new_agents(
    _: User = Depends(get_current_user),
    days: int = Query(default=7, ge=1, le=365, description="Agents created in the last N days"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    registry_service: RegistryService = Depends(),
):
    """List recently published agents (new in the last N days).
    :param _: User
    :param days: int
    :param limit: int
    :param offset: int
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    query = AgentSearchQuery(
        sort="created_at",
        order="desc",
        days=days,
        limit=limit,
        offset=offset,
    )
    agents = await registry_service.list_agents(query)
    agent_ids = [a.id for a in agents]
    rating_aggregates = await registry_service.get_rating_aggregates_bulk(agent_ids)
    quality_metrics = await registry_service.get_agent_quality_metrics_bulk(agent_ids)

    def _rating(agent_id):
        avg, count = rating_aggregates.get(agent_id, (None, 0))
        return (round(avg, 2) if avg is not None else None, count)

    def _quality(agent_id):
        sr, avg_lat, count = quality_metrics.get(agent_id, (None, None, 0))
        return (
            round(sr, 2) if sr is not None else None,
            round(avg_lat, 2) if avg_lat is not None else None,
            count,
        )

    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            category=getattr(agent, "category", None),
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            capabilities=[CapabilitySchema.from_capability(cap) for cap in agent.capabilities],
            rating_avg=_rating(agent.id)[0],
            rating_count=_rating(agent.id)[1],
            quality_success_rate=_quality(agent.id)[0],
            quality_avg_latency_ms=_quality(agent.id)[1],
            quality_invocation_count=_quality(agent.id)[2],
        )
        for agent in agents
    ]


@router.get("/agents/trending", response_model=List[AgentListResponse])
async def list_trending_agents(
    _: User = Depends(get_current_user),
    window_days: int = Query(default=7, ge=1, le=365, description="Invocation count in the last N days"),
    limit: int = Query(default=20, ge=1, le=100),
    registry_service: RegistryService = Depends(),
):
    """List agents ordered by invocation count in the last N days (trending/popular).
    :param _: User
    :param window_days: int
    :param limit: int
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    results = await registry_service.get_trending_agents(window_days=window_days, limit=limit)
    if not results:
        return []
    agents = [agent for agent, _ in results]
    agent_ids = [a.id for a in agents]
    rating_aggregates = await registry_service.get_rating_aggregates_bulk(agent_ids)
    quality_metrics = await registry_service.get_agent_quality_metrics_bulk(agent_ids, window_days=window_days)
    count_by_id = {agent.id: count for agent, count in results}

    def _rating(agent_id):
        avg, count = rating_aggregates.get(agent_id, (None, 0))
        return (round(avg, 2) if avg is not None else None, count)

    def _quality(agent_id):
        sr, avg_lat, inv_count = quality_metrics.get(agent_id, (None, None, 0))
        return (
            round(sr, 2) if sr is not None else None,
            round(avg_lat, 2) if avg_lat is not None else None,
            inv_count,
        )

    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            category=getattr(agent, "category", None),
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            capabilities=[CapabilitySchema.from_capability(cap) for cap in agent.capabilities],
            rating_avg=_rating(agent.id)[0],
            rating_count=_rating(agent.id)[1],
            quality_success_rate=_quality(agent.id)[0],
            quality_avg_latency_ms=_quality(agent.id)[1],
            quality_invocation_count=_quality(agent.id)[2],
            invocation_count=count_by_id.get(agent.id),
        )
        for agent in agents
    ]


@router.post("/agents/{agent_id}/rate", response_model=RatingResponse)
async def rate_agent(
    agent_id: str,
    body: RateRequest,
    current_user: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """Submit or update your rating for an agent (or a capability).
    :param agent_id: str - Agent ID (e.g. agent:ns:name:version)
    :param body: RateRequest - score (1-5), optional capability_id, optional comment
    :param current_user: User
    :param registry_service: RegistryService
    :return: RatingResponse
    """
    try:
        rating = await registry_service.rate_agent(
            agent_id=agent_id,
            user_id=current_user.id,
            score=body.score,
            capability_id=body.capability_id,
            comment=body.comment,
        )
        return RatingResponse(
            id=rating.id,
            user_id=rating.user_id,
            agent_id=rating.agent_id,
            capability_id=rating.capability_id,
            score=rating.score,
            comment=rating.comment,
            created_at=rating.created_at,
            updated_at=rating.updated_at,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise NotFoundException(str(e))
        raise BadRequestException(str(e))


@router.get(
    "/agents/{agent_id}/ratings",
    response_model=List[RatingResponse],
    tags=["Public"],
)
async def list_agent_ratings(
    agent_id: str,
    registry_service: RegistryService = Depends(),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List recent ratings for an agent (public, no auth).

    Intended for showcasing agent reviews in the frontend. Returns score,
    optional comment, and timestamps; user_id is an opaque UUID. No authentication
    required.
    :param agent_id: str
    :param registry_service: RegistryService
    :param limit: int
    :param offset: int
    :return: List[RatingResponse]
    """
    agent = await registry_service.get_agent(agent_id)
    if not agent:
        raise NotFoundException("Agent")
    ratings = await registry_service.get_ratings_for_agent(agent.id, limit=limit, offset=offset)
    return [
        RatingResponse(
            id=r.id,
            user_id=r.user_id,
            agent_id=r.agent_id,
            capability_id=r.capability_id,
            score=r.score,
            comment=r.comment,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in ratings
    ]


@router.get("/agents/{agent_id}", response_model=AgentResponse, tags=["Public"])
async def get_agent(
    agent_id: str,
    registry_service: RegistryService = Depends(),
):
    """Get agent details by agent_id (public, no auth).

    Intended for showcasing agents in the frontend. Returns only public fields
    (no owner/brand PII). No authentication required.
    :param agent_id: str
    :param registry_service: RegistryService
    :return: AgentResponse
    """
    
    agent = await registry_service.get_agent(agent_id)
    if not agent:
        raise NotFoundException("Agent")

    rating_avg, rating_count = await registry_service.get_rating_aggregate(agent.id)
    quality_sr, quality_lat, quality_count = await registry_service.get_agent_quality_metrics(agent.id)

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
        capabilities=[CapabilitySchema.from_capability(cap) for cap in agent.capabilities],
        requirements=requirements_from_orm(agent.requirements),
        category=getattr(agent, "category", None),
        rating_avg=round(rating_avg, 2) if rating_avg is not None else None,
        rating_count=rating_count,
        quality_success_rate=round(quality_sr, 2) if quality_sr is not None else None,
        quality_avg_latency_ms=round(quality_lat, 2) if quality_lat is not None else None,
        quality_invocation_count=quality_count,
    )


@router.put("/agents/{agent_uuid}", response_model=AgentResponse)
async def update_agent(
    agent_uuid: UUID,
    agent_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    enhance_manifest: bool = Query(default=True, description="Whether to enhance manifest text with LLM"),
    registry_service: RegistryService = Depends(),
):
    """Update an agent (owner only).
    :param agent_uuid: UUID
    :param agent_data: AgentUpdate
    :param current_user: User
    :param enhance_manifest: bool - Whether to enhance manifest text with LLM
    :param registry_service: RegistryService
    :return: AgentResponse
    """
    
    try:
        agent = await registry_service.update_agent(
            agent_uuid,
            agent_data.manifest,
            current_user.id,
            enhance_manifest=enhance_manifest,
            brand_id=agent_data.brand_id,
        )
        
        rating_avg, rating_count = await registry_service.get_rating_aggregate(agent.id)
        quality_sr, quality_lat, quality_count = await registry_service.get_agent_quality_metrics(agent.id)
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
            capabilities=[CapabilitySchema.from_capability(cap) for cap in agent.capabilities],
            requirements=requirements_from_orm(agent.requirements),
            category=getattr(agent, "category", None),
            rating_avg=round(rating_avg, 2) if rating_avg is not None else None,
            rating_count=rating_count,
            quality_success_rate=round(quality_sr, 2) if quality_sr is not None else None,
            quality_avg_latency_ms=round(quality_lat, 2) if quality_lat is not None else None,
            quality_invocation_count=quality_count,
        )
    except ValueError as e:
        raise BadRequestException(str(e))


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
            raise NotFoundException("Agent")
    except ValueError as e:
        raise ForbiddenException(str(e))


@router.get("/discover", response_model=List[AgentListResponse])
async def semantic_discover(
    query: str = Query(..., description="Natural language query for semantic search"),
    limit: int = Query(default=10, ge=1, le=50),
    similarity_threshold: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=2.0,
        description="Maximum cosine distance (0.0=same, 2.0=opposite). Lower values = more strict matching. None = no threshold (return all results ordered by similarity).",
    ),
    rank_by: str = Query(
        default="balanced",
        description="Ranking: similarity_only, balanced (similarity + quality + recency), quality_first.",
    ),
    enhance_query: bool = Query(default=True, description="Whether to enhance query with LLM"),
    registry_service: RegistryService = Depends(),
):
    """
    Semantic discovery of agents using vector similarity, optionally re-ranked by quality and recency.
    :param query: str - Natural language query
    :param limit: int - Maximum number of results
    :param similarity_threshold: Optional[float] - Maximum cosine distance for matching (None = no threshold)
    :param rank_by: str - similarity_only | balanced | quality_first
    :param enhance_query: bool - Whether to enhance query with LLM
    :param registry_service: RegistryService
    :return: List[AgentListResponse]
    """
    discover_query = DiscoverQuery(
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
        rank_by=rank_by,
    )
    results = await registry_service.semantic_discover(discover_query, enhance_query=enhance_query)
    agent_ids = [agent.id for agent, _ in results]
    rating_aggregates = await registry_service.get_rating_aggregates_bulk(agent_ids)
    quality_metrics = await registry_service.get_agent_quality_metrics_bulk(agent_ids)

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
            category=getattr(agent, "category", None),
            similarity_score=score,
            rating_avg=round(rating_aggregates.get(agent.id, (None, 0))[0], 2) if rating_aggregates.get(agent.id, (None, 0))[0] is not None else None,
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_success_rate=round(quality_metrics.get(agent.id, (None, None, 0))[0], 2) if quality_metrics.get(agent.id, (None, None, 0))[0] is not None else None,
            quality_avg_latency_ms=round(quality_metrics.get(agent.id, (None, None, 0))[1], 2) if quality_metrics.get(agent.id, (None, None, 0))[1] is not None else None,
            quality_invocation_count=quality_metrics.get(agent.id, (None, None, 0))[2],
        )
        for agent, score in results
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
    agent_ids = [a.id for a in agents]
    rating_aggregates = await registry_service.get_rating_aggregates_bulk(agent_ids)
    quality_metrics = await registry_service.get_agent_quality_metrics_bulk(agent_ids)

    return [
        AgentListResponse(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            version=agent.version,
            tags=agent.tags,
            category=getattr(agent, "category", None),
            trust_verification=agent.trust_verification,
            is_active=agent.is_active,
            created_at=agent.created_at,
            rating_avg=round(rating_aggregates.get(agent.id, (None, 0))[0], 2) if rating_aggregates.get(agent.id, (None, 0))[0] is not None else None,
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_success_rate=round(quality_metrics.get(agent.id, (None, None, 0))[0], 2) if quality_metrics.get(agent.id, (None, None, 0))[0] is not None else None,
            quality_avg_latency_ms=round(quality_metrics.get(agent.id, (None, None, 0))[1], 2) if quality_metrics.get(agent.id, (None, None, 0))[1] is not None else None,
            quality_invocation_count=quality_metrics.get(agent.id, (None, None, 0))[2],
        )
        for agent in agents
    ]
