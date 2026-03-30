"""Registry routes for agent management."""

import asyncio
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import get_current_user
from src.exceptions import BadRequestException, ForbiddenException, NotFoundException
from src.models.auth import User
from src.schemas.registry import (
    AgentListResponse,
    AgentRegistration,
    AgentResponse,
    AgentSearchQuery,
    AgentUpdate,
    CredentialSetRequest,
    DiscoverQuery,
    GenerateAgentRequest,
    RateRequest,
    RatingResponse,
)
from src.services.registry import RegistryService
from src.utilities.manifest_generator import ManifestGenerationError, generate_agent_from_description

router = APIRouter(prefix="/registry", tags=["Registry"])


def _build_agent_response(agent, rating_avg=None, rating_count=0, quality_sr=None, quality_lat=None, quality_count=0, has_credentials=False) -> AgentResponse:
    return AgentResponse(
        id=agent.id,
        agent_id=agent.agent_id,
        name=agent.name,
        description=agent.description,
        version=getattr(agent, "version", "1.0.0") or "1.0.0",
        endpoint=agent.invoke_endpoint,
        auth_type=agent.auth_type,
        input_schema=agent.input_schema,
        tags=agent.tags,
        category=getattr(agent, "category", None),
        trust_verification=agent.trust_verification,
        is_active=agent.is_active,
        is_brand_agent=getattr(agent, "is_brand_agent", False) or False,
        has_credentials=has_credentials,
        pricing_strategy=getattr(agent, "pricing_strategy", None),
        base_price=getattr(agent, "base_price", None),
        pricing_enabled=getattr(agent, "pricing_enabled", False) or False,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        rating_avg=round(rating_avg, 2) if rating_avg is not None else None,
        rating_count=rating_count,
        quality_success_rate=round(quality_sr, 2) if quality_sr is not None else None,
        quality_avg_latency_ms=round(quality_lat, 2) if quality_lat is not None else None,
        quality_invocation_count=quality_count,
    )


def _build_list_response(agent, rating_avg=None, rating_count=0, quality_sr=None, quality_lat=None, quality_count=0, similarity_score=None, invocation_count=None, has_credentials=False) -> AgentListResponse:
    return AgentListResponse(
        id=agent.id,
        agent_id=agent.agent_id,
        name=agent.name,
        description=agent.description,
        version=getattr(agent, "version", "1.0.0") or "1.0.0",
        endpoint=agent.invoke_endpoint,
        auth_type=agent.auth_type,
        input_schema=agent.input_schema,
        tags=agent.tags,
        category=getattr(agent, "category", None),
        trust_verification=agent.trust_verification,
        is_active=agent.is_active,
        is_brand_agent=getattr(agent, "is_brand_agent", False) or False,
        has_credentials=has_credentials,
        pricing_strategy=getattr(agent, "pricing_strategy", None),
        base_price=getattr(agent, "base_price", None),
        pricing_enabled=getattr(agent, "pricing_enabled", False) or False,
        created_at=agent.created_at,
        similarity_score=similarity_score,
        rating_avg=round(rating_avg, 2) if rating_avg is not None else None,
        rating_count=rating_count,
        quality_success_rate=round(quality_sr, 2) if quality_sr is not None else None,
        quality_avg_latency_ms=round(quality_lat, 2) if quality_lat is not None else None,
        quality_invocation_count=quality_count,
        invocation_count=invocation_count,
    )


@router.post("/agents", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def register_agent(
    agent_data: AgentRegistration,
    current_user: User = Depends(get_current_user),
    enhance: bool = Query(default=True, description="Whether to enhance agent text with LLM for better search"),
    registry_service: RegistryService = Depends(),
):
    """Register a new agent. Only name, description, and endpoint are required."""
    try:
        agent = await registry_service.register_agent(
            agent_data,
            current_user.id,
            enhance=enhance,
        )
        return _build_agent_response(agent)
    except ValueError as e:
        raise BadRequestException(str(e))


@router.post("/generate", response_model=dict)
async def generate_agent(
    body: GenerateAgentRequest,
    _: User = Depends(get_current_user),
):
    """Generate an agent configuration from a natural language description using AI.

    Returns a JSON object you can edit and POST to /registry/agents.
    Requires OPENAI_API_KEY to be configured.
    """
    try:
        registration = await generate_agent_from_description(
            body.description,
            endpoint=body.endpoint,
        )
        return registration.model_dump()
    except ManifestGenerationError as e:
        err_msg = str(e).lower()
        if "api key" in err_msg or "openai" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI generation requires OpenAI API key.",
            ) from e
        raise BadRequestException(str(e))


@router.get("/agents", response_model=List[AgentListResponse])
async def list_agents(
    _: User = Depends(get_current_user),
    tags: List[str] = Query(default=None),
    search: str = Query(default=None),
    category: Optional[str] = Query(default=None),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    days: Optional[int] = Query(default=None, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    registry_service: RegistryService = Depends(),
):
    """List and search agents."""
    query = AgentSearchQuery(
        tags=tags,
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
    rating_aggregates, quality_metrics = await asyncio.gather(
        registry_service.get_rating_aggregates_bulk(agent_ids),
        registry_service.get_agent_quality_metrics_bulk(agent_ids),
    )

    return [
        _build_list_response(
            agent,
            rating_avg=rating_aggregates.get(agent.id, (None, 0))[0],
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_sr=quality_metrics.get(agent.id, (None, None, 0))[0],
            quality_lat=quality_metrics.get(agent.id, (None, None, 0))[1],
            quality_count=quality_metrics.get(agent.id, (None, None, 0))[2],
        )
        for agent in agents
    ]


@router.get("/agents/new", response_model=List[AgentListResponse])
async def list_new_agents(
    _: User = Depends(get_current_user),
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    registry_service: RegistryService = Depends(),
):
    """List recently published agents."""
    query = AgentSearchQuery(sort="created_at", order="desc", days=days, limit=limit, offset=offset)
    agents = await registry_service.list_agents(query)
    agent_ids = [a.id for a in agents]
    rating_aggregates, quality_metrics = await asyncio.gather(
        registry_service.get_rating_aggregates_bulk(agent_ids),
        registry_service.get_agent_quality_metrics_bulk(agent_ids),
    )

    return [
        _build_list_response(
            agent,
            rating_avg=rating_aggregates.get(agent.id, (None, 0))[0],
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_sr=quality_metrics.get(agent.id, (None, None, 0))[0],
            quality_lat=quality_metrics.get(agent.id, (None, None, 0))[1],
            quality_count=quality_metrics.get(agent.id, (None, None, 0))[2],
        )
        for agent in agents
    ]


@router.get("/agents/trending", response_model=List[AgentListResponse])
async def list_trending_agents(
    _: User = Depends(get_current_user),
    window_days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
    registry_service: RegistryService = Depends(),
):
    """List agents ordered by invocation count (trending/popular)."""
    results = await registry_service.get_trending_agents(window_days=window_days, limit=limit)
    if not results:
        return []
    agents = [agent for agent, _ in results]
    agent_ids = [a.id for a in agents]
    rating_aggregates, quality_metrics = await asyncio.gather(
        registry_service.get_rating_aggregates_bulk(agent_ids),
        registry_service.get_agent_quality_metrics_bulk(agent_ids, window_days=window_days),
    )
    count_by_id = {agent.id: count for agent, count in results}

    return [
        _build_list_response(
            agent,
            rating_avg=rating_aggregates.get(agent.id, (None, 0))[0],
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_sr=quality_metrics.get(agent.id, (None, None, 0))[0],
            quality_lat=quality_metrics.get(agent.id, (None, None, 0))[1],
            quality_count=quality_metrics.get(agent.id, (None, None, 0))[2],
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
    """Submit or update your rating for an agent."""
    try:
        rating = await registry_service.rate_agent(
            agent_id=agent_id,
            user_id=current_user.id,
            score=body.score,
            comment=body.comment,
        )
        return RatingResponse(
            id=rating.id,
            user_id=rating.user_id,
            agent_id=rating.agent_id,
            score=rating.score,
            comment=rating.comment,
            created_at=rating.created_at,
            updated_at=rating.updated_at,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise NotFoundException(str(e))
        raise BadRequestException(str(e))


@router.get("/agents/{agent_id}/ratings", response_model=List[RatingResponse])
async def list_agent_ratings(
    agent_id: str,
    _: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List recent ratings for an agent."""
    agent = await registry_service.get_agent(agent_id)
    if not agent:
        raise NotFoundException("Agent")
    ratings = await registry_service.get_ratings_for_agent(agent.id, limit=limit, offset=offset)
    return [
        RatingResponse(
            id=r.id,
            user_id=r.user_id,
            agent_id=r.agent_id,
            score=r.score,
            comment=r.comment,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in ratings
    ]


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    _: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """Get agent details by agent_id."""
    agent = await registry_service.get_agent(agent_id)
    if not agent:
        raise NotFoundException("Agent")

    (rating_avg, rating_count), (quality_sr, quality_lat, quality_count), agent_has_credentials = await asyncio.gather(
        registry_service.get_rating_aggregate(agent.id),
        registry_service.get_agent_quality_metrics(agent.id),
        registry_service.has_credentials(agent.id, agent.auth_type),
    )

    return _build_agent_response(
        agent,
        rating_avg=rating_avg,
        rating_count=rating_count,
        quality_sr=quality_sr,
        quality_lat=quality_lat,
        quality_count=quality_count,
        has_credentials=agent_has_credentials,
    )


@router.put("/agents/{agent_uuid}", response_model=AgentResponse)
async def update_agent(
    agent_uuid: UUID,
    agent_data: AgentUpdate,
    current_user: User = Depends(get_current_user),
    enhance: bool = Query(default=True),
    registry_service: RegistryService = Depends(),
):
    """Update an agent (owner only). All fields optional — only provided fields change."""
    try:
        agent = await registry_service.update_agent(
            agent_uuid,
            agent_data,
            current_user.id,
            enhance=enhance,
        )
        (rating_avg, rating_count), (quality_sr, quality_lat, quality_count), agent_has_credentials = await asyncio.gather(
            registry_service.get_rating_aggregate(agent.id),
            registry_service.get_agent_quality_metrics(agent.id),
            registry_service.has_credentials(agent.id, agent.auth_type),
        )
        return _build_agent_response(
            agent,
            rating_avg=rating_avg,
            rating_count=rating_count,
            quality_sr=quality_sr,
            quality_lat=quality_lat,
            quality_count=quality_count,
            has_credentials=agent_has_credentials,
        )
    except ValueError as e:
        raise BadRequestException(str(e))


@router.post("/agents/{agent_uuid}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def set_agent_credential(
    agent_uuid: UUID,
    body: CredentialSetRequest,
    current_user: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """Set or update per-agent API key or bearer token (owner only)."""
    try:
        await registry_service.set_agent_credential(
            agent_uuid,
            current_user.id,
            body.credential_type,
            body.value,
            auth_header=body.auth_header,
            auth_scheme=body.auth_scheme,
        )
    except ValueError as e:
        if "not found" in str(e).lower():
            raise NotFoundException(str(e))
        raise ForbiddenException(str(e))


@router.delete("/agents/{agent_uuid}/credentials", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_credentials(
    agent_uuid: UUID,
    current_user: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """Delete all per-agent credentials (owner only)."""
    try:
        await registry_service.delete_agent_credentials(agent_uuid, current_user.id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise NotFoundException(str(e))
        raise ForbiddenException(str(e))


@router.delete("/agents/{agent_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_uuid: UUID,
    current_user: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """Delete an agent (owner only)."""
    try:
        success = await registry_service.delete_agent(agent_uuid, current_user.id)
        if not success:
            raise NotFoundException("Agent")
    except ValueError as e:
        raise ForbiddenException(str(e))


@router.get("/discover", response_model=List[AgentListResponse])
async def semantic_discover(
    _: User = Depends(get_current_user),
    query: str = Query(..., description="Natural language query for semantic search"),
    limit: int = Query(default=10, ge=1, le=50),
    similarity_threshold: Optional[float] = Query(
        default=None, ge=0.0, le=2.0,
        description="Maximum cosine distance (0.0=same, 2.0=opposite). None = no threshold.",
    ),
    rank_by: str = Query(default="balanced", description="similarity_only | balanced | quality_first"),
    enhance_query: bool = Query(default=True, description="Whether to enhance query with LLM"),
    registry_service: RegistryService = Depends(),
):
    """Semantic discovery of agents using vector similarity."""
    discover_query = DiscoverQuery(
        query=query,
        limit=limit,
        similarity_threshold=similarity_threshold,
        rank_by=rank_by,
    )
    results = await registry_service.semantic_discover(discover_query, enhance_query=enhance_query)
    agent_ids = [agent.id for agent, _ in results]
    rating_aggregates, quality_metrics = await asyncio.gather(
        registry_service.get_rating_aggregates_bulk(agent_ids),
        registry_service.get_agent_quality_metrics_bulk(agent_ids),
    )

    return [
        _build_list_response(
            agent,
            rating_avg=rating_aggregates.get(agent.id, (None, 0))[0],
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_sr=quality_metrics.get(agent.id, (None, None, 0))[0],
            quality_lat=quality_metrics.get(agent.id, (None, None, 0))[1],
            quality_count=quality_metrics.get(agent.id, (None, None, 0))[2],
            similarity_score=score,
        )
        for agent, score in results
    ]


@router.get("/my-agents", response_model=List[AgentListResponse])
async def get_agents_by_user_id(
    current_user: User = Depends(get_current_user),
    registry_service: RegistryService = Depends(),
):
    """Get current user's agents."""
    agents = await registry_service.get_agents_by_user_id(current_user.id)
    agent_ids = [a.id for a in agents]
    rating_aggregates, quality_metrics, cred_status = await asyncio.gather(
        registry_service.get_rating_aggregates_bulk(agent_ids),
        registry_service.get_agent_quality_metrics_bulk(agent_ids),
        registry_service.get_credential_status_bulk({a.id: a.auth_type for a in agents}),
    )

    return [
        _build_list_response(
            agent,
            rating_avg=rating_aggregates.get(agent.id, (None, 0))[0],
            rating_count=rating_aggregates.get(agent.id, (None, 0))[1],
            quality_sr=quality_metrics.get(agent.id, (None, None, 0))[0],
            quality_lat=quality_metrics.get(agent.id, (None, None, 0))[1],
            quality_count=quality_metrics.get(agent.id, (None, None, 0))[2],
            has_credentials=cred_status.get(agent.id, False),
        )
        for agent in agents
    ]
