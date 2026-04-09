"""Resolve step targets to concrete agent IDs.

Direct references (e.g. ``agent: weather-forecaster-v1``) pass through.
Search references (e.g. ``agent: "search:translate to Spanish"``) call
wisdom's RegistryService.semantic_discover() directly.

When a circuit breaker is provided, agents whose breakers are open are
treated as unavailable — excluded from search results and rejected for
direct references.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.workflow.exceptions import AgentUnavailableError
from src.workflow.utils.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

SEARCH_PREFIX = "search:"


@dataclass
class ResolvedTarget:
    agent_id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] | None = None


class Resolver:
    def __init__(self, circuit_breaker: CircuitBreaker) -> None:
        self._circuit_breaker = circuit_breaker
        self._cache: dict[str, ResolvedTarget] = {}

    async def resolve(
        self, ref: str, exclude_ids: list[str] | None = None
    ) -> ResolvedTarget:
        """Resolve a reference string to a concrete agent target.

        Args:
            ref: Either a direct agent ID or ``search:<natural language query>``.
            exclude_ids: Agent IDs to filter out (used by semantic fallback).
        """
        cache_key = ref if not exclude_ids else f"{ref}|!{'|!'.join(exclude_ids)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Safety check: reject if platform is halted
        from src.services.safety import check_platform_halt
        await check_platform_halt()

        if ref.startswith(SEARCH_PREFIX):
            query = ref[len(SEARCH_PREFIX):].strip()
            target = await self._discover(query, exclude_ids or [])
        else:
            available = await self._circuit_breaker.is_available(ref)
            if not available:
                raise AgentUnavailableError(
                    f"Agent '{ref}' is unavailable (circuit breaker open)"
                )
            target = ResolvedTarget(agent_id=ref, name=ref)

        self._cache[cache_key] = target
        return target

    async def invoke(
        self, agent_id: str, input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Invoke an agent directly via wisdom's BrokerService."""
        from src.database import async_session_factory
        from src.services.broker import BrokerService
        from src.repositories.broker import BrokerConfigRepository
        from src.repositories.invocation_log import InvocationLogRepository
        from src.repositories.registry import RegistryRepository
        from src.repositories.conversation import ConversationRepository
        from src.repositories.message import MessageRepository
        from src.repositories.brand import BrandRepository
        from src.schemas.broker import InvokeRequest

        async with async_session_factory() as session:
            broker = BrokerService(
                invocation_log_repository=InvocationLogRepository(session),
                broker_config_repository=BrokerConfigRepository(session),
                registry_repository=RegistryRepository(session),
                conversation_repository=ConversationRepository(session),
                message_repository=MessageRepository(session),
                brand_repository=BrandRepository(session),
            )
            # Use a system-level user ID for workflow invocations
            from src.models.auth import User
            from sqlalchemy import select
            result = await session.execute(select(User).limit(1))
            system_user = result.scalar_one_or_none()
            if not system_user:
                return {"success": False, "data": None, "latency_ms": 0, "status_code": 500}

            invoke_req = InvokeRequest(agent_id=agent_id, input=input_data)
            response = await broker.invoke_agent(invoke_req, caller_user_id=system_user.id)
            await session.commit()

        return {
            "success": response.success,
            "data": response.data,
            "latency_ms": response.latency_ms,
            "status_code": response.status_code,
        }

    async def _discover(
        self, query: str, exclude_ids: list[str]
    ) -> ResolvedTarget:
        """Discover agents using wisdom's RegistryService.semantic_discover()."""
        from src.database import async_session_factory
        from src.services.registry import RegistryService
        from src.repositories.registry import RegistryRepository
        from src.repositories.invocation_log import InvocationLogRepository
        from src.repositories.brand import BrandRepository
        from src.utilities.embedding import EmbeddingService
        from src.schemas.registry import DiscoverQuery

        cb_excluded: list[str] = list(exclude_ids)

        async with async_session_factory() as session:
            registry_service = RegistryService(
                registry_repository=RegistryRepository(session),
                invocation_log_repository=InvocationLogRepository(session),
                embedding_service=EmbeddingService(),
                brand_repository=BrandRepository(session),
            )
            discover_query = DiscoverQuery(query=query, limit=5)
            results = await registry_service.semantic_discover(discover_query)

        for agent, _distance in results:
            if agent.agent_id in cb_excluded:
                continue
            if not agent.is_active:
                logger.info("Skipping agent '%s' — inactive", agent.agent_id)
                cb_excluded.append(agent.agent_id)
                continue
            available = await self._circuit_breaker.is_available(agent.agent_id)
            if not available:
                logger.info(
                    "Skipping agent '%s' — circuit breaker open",
                    agent.agent_id,
                )
                cb_excluded.append(agent.agent_id)
                continue
            logger.info(
                "Resolved search '%s' -> agent '%s' (%s)",
                query,
                agent.agent_id,
                agent.name,
            )
            return ResolvedTarget(
                agent_id=agent.agent_id,
                name=agent.name,
                description=agent.description or "",
                input_schema=agent.input_schema,
            )
        raise RuntimeError(
            f"No agents found for query '{query}' "
            f"(excluded: {cb_excluded})"
        )
