"""Executor utility: run one step (discover -> select -> invoke via Broker; fallback)."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.models.registry import Agent
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.schemas.registry import DiscoverQuery
from src.utilities.planner import StepSpec


@dataclass
class ExecutorContext:
    """Context for executing a step: user, integration, conversation/message, fallback."""

    user_id: UUID
    integration_id: Optional[UUID]
    conversation_id: Optional[UUID]
    message_id: Optional[UUID]
    fallback_agent_id: Optional[str]
    external_user_id: Optional[str] = None


@dataclass
class StepResult:
    """Result of executing one step."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    agent_id: Optional[str] = None
    conversation_id: Optional[UUID] = None


class Executor:
    """
    Executes a single step: discover (Registry) -> select agent -> invoke (Broker).
    Handles fallback when discovery returns no candidates; respects allowlist.
    """

    def __init__(
        self,
        registry_service: Any,  # RegistryService
        broker_service: Any,  # BrokerService
        embedding_service: Any,  # EmbeddingService
        broker_config_repository: Any,  # BrokerConfigRepository
    ):
        self.registry_service = registry_service
        self.broker_service = broker_service
        self.embedding_service = embedding_service
        self.broker_config_repository = broker_config_repository

    async def execute_step(
        self,
        step: StepSpec,
        context: ExecutorContext,
    ) -> StepResult:
        """
        Run one step: discover agents, select (or use fallback), invoke via Broker.
        :param step: StepSpec
        :param context: ExecutorContext
        :return: StepResult
        """
        # 1. Discover agents via semantic search
        discover_query = DiscoverQuery(
            query=step.description,
            limit=5,
            similarity_threshold=None,
        )
        candidates: List[tuple[Agent, float]] = (
            await self.registry_service.semantic_discover(
                discover_query,
                enhance_query=True,
            )
        )

        # 2. Load broker config for allowlist
        config = await self.broker_config_repository.get_effective_config(
            context.integration_id
        )
        allowed_agent_ids: Optional[List[UUID]] = None
        if config and config.allowed_agent_ids and len(config.allowed_agent_ids) > 0:
            allowed_agent_ids = config.allowed_agent_ids

        # 3. Filter candidates by allowlist
        if allowed_agent_ids is not None:
            candidates = [
                (agent, dist)
                for agent, dist in candidates
                if agent.id in allowed_agent_ids
            ]

        # 4. If no candidates, try fallback
        if not candidates:
            if context.fallback_agent_id:
                fallback_agent = await self.registry_service.get_agent(
                    context.fallback_agent_id
                )
                if not fallback_agent or not fallback_agent.is_active:
                    return StepResult(
                        success=False,
                        error="No agents found and fallback agent not found or inactive.",
                    )
                if allowed_agent_ids is not None and fallback_agent.id not in allowed_agent_ids:
                    return StepResult(
                        success=False,
                        error="No agents found and fallback not allowed for this integration.",
                    )
                return await self._invoke_one(
                    context.fallback_agent_id,
                    step.input,
                    context,
                )
            return StepResult(
                success=False,
                error="No suitable agent found for this step; consider configuring a fallback agent.",
            )

        # 5. Try each candidate in order until one succeeds
        for agent, _ in candidates:
            result = await self._invoke_one(
                agent.agent_id,
                step.input,
                context,
            )
            if result.success:
                return result

        # 6. All candidates failed; try fallback
        if context.fallback_agent_id:
            fallback_agent = await self.registry_service.get_agent(
                context.fallback_agent_id
            )
            if fallback_agent and fallback_agent.is_active:
                if allowed_agent_ids is None or fallback_agent.id in allowed_agent_ids:
                    return await self._invoke_one(
                        context.fallback_agent_id,
                        step.input,
                        context,
                    )
            return StepResult(
                success=False,
                error="All candidates failed and fallback not available or not allowed.",
            )

        return StepResult(
            success=False,
            error="All discovered agents failed for this step.",
        )

    async def _invoke_one(
        self,
        agent_id: str,
        step_input: Dict[str, Any],
        context: ExecutorContext,
    ) -> StepResult:
        """Invoke one agent via Broker and return StepResult."""
        invoke_request = InvokeRequest(
            agent_id=agent_id,
            input=step_input,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            external_user_id=context.external_user_id,
        )
        response: InvokeResponse = await self.broker_service.invoke_agent(
            invoke_request,
            caller_user_id=context.user_id,
            integration_id=context.integration_id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
        )
        if response.success:
            return StepResult(
                success=True,
                data=response.data,
                agent_id=agent_id,
                conversation_id=response.conversation_id,
            )
        return StepResult(
            success=False,
            error=response.error or "Agent invocation failed",
            agent_id=agent_id,
            conversation_id=response.conversation_id,
        )
