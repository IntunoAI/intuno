"""Recovery manager — retry with backoff and semantic fallback.

Retry with configurable exponential backoff.  When retries are exhausted and
``semantic_fallback`` is enabled, re-discover an alternative agent via the
resolver and retry with it (up to ``max_alternatives`` times).
"""


import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends

from src.workflow.exceptions import StepExecutionError
from src.workflow.models.dsl import RecoveryConfig
from src.workflow.utils.circuit_breaker import CircuitBreaker
from src.workflow.utils.concurrency import ConcurrencyLimiter, RedisSemaphore
from src.workflow.utils.resolver import SEARCH_PREFIX, Resolver, ResolvedTarget

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Outcome of a recovery-managed invocation."""

    data: dict[str, Any]
    final_target: ResolvedTarget
    attempts_total: int
    fallback_used: bool
    tried_agents: list[str] = field(default_factory=list)


class RecoveryManager:
    def __init__(
        self,
        resolver: Resolver = Depends(),
        circuit_breaker: CircuitBreaker = Depends(),
        concurrency_limiter: ConcurrencyLimiter = Depends(),
    ) -> None:
        self._resolver = resolver
        self._circuit_breaker = circuit_breaker
        self._limiter = concurrency_limiter

    async def execute_with_recovery(
        self,
        target: ResolvedTarget,
        input_data: dict[str, Any],
        recovery_config: RecoveryConfig,
        original_ref: str | None = None,
        agent_concurrency_limit: int | None = None,
    ) -> RecoveryResult:
        """Invoke an agent with retry + semantic fallback.

        1. Retry the primary target up to ``max_attempts`` times.
        2. If retries are exhausted and ``semantic_fallback`` is enabled,
           re-discover an alternative agent (excluding already-tried ones)
           and repeat, up to ``max_alternatives`` alternatives.
        3. Return a ``RecoveryResult`` with the final target and data.
        """
        total_attempts = 0
        tried_ids: list[str] = []
        current_target = target

        result, attempts = await self._try_agent(
            current_target, input_data, recovery_config, agent_concurrency_limit,
        )
        total_attempts += attempts
        tried_ids.append(current_target.agent_id)

        if result is not None:
            return RecoveryResult(
                data=result,
                final_target=current_target,
                attempts_total=total_attempts,
                fallback_used=False,
                tried_agents=tried_ids,
            )

        if not recovery_config.semantic_fallback:
            raise StepExecutionError(
                f"Agent '{current_target.agent_id}' failed after "
                f"{recovery_config.max_attempts} attempts",
                attempt=total_attempts,
            )

        search_query = self._build_fallback_query(original_ref, current_target)
        if search_query is None:
            raise StepExecutionError(
                f"Agent '{current_target.agent_id}' failed and semantic "
                f"fallback cannot proceed — no search query or description "
                f"available to discover alternatives",
                attempt=total_attempts,
            )

        for alt_idx in range(recovery_config.max_alternatives):
            logger.info(
                "Semantic fallback %d/%d: searching '%s' (excluding %s)",
                alt_idx + 1,
                recovery_config.max_alternatives,
                search_query,
                tried_ids,
            )
            try:
                alt_target = await self._resolver.resolve(
                    search_query, exclude_ids=tried_ids
                )
            except RuntimeError:
                logger.warning(
                    "No more alternative agents found for '%s'", search_query
                )
                break

            result, attempts = await self._try_agent(
                alt_target, input_data, recovery_config, agent_concurrency_limit,
            )
            total_attempts += attempts
            tried_ids.append(alt_target.agent_id)

            if result is not None:
                return RecoveryResult(
                    data=result,
                    final_target=alt_target,
                    attempts_total=total_attempts,
                    fallback_used=True,
                    tried_agents=tried_ids,
                )

        raise StepExecutionError(
            f"All agents failed (tried: {tried_ids}) after "
            f"{total_attempts} total attempts",
            attempt=total_attempts,
        )

    async def _try_agent(
        self,
        target: ResolvedTarget,
        input_data: dict[str, Any],
        recovery_config: RecoveryConfig,
        agent_concurrency_limit: int | None = None,
    ) -> tuple[dict[str, Any] | None, int]:
        """Retry a single agent up to ``max_attempts`` times.

        Returns ``(result_dict, attempts)`` on success or
        ``(None, max_attempts)`` when all retries are exhausted.
        Every attempt feeds the circuit breaker.
        """
        last_error: Exception | None = None
        sem: RedisSemaphore | None = None
        if agent_concurrency_limit:
            sem = self._limiter.agent_semaphore(
                target.agent_id, agent_concurrency_limit,
            )

        for attempt in range(1, recovery_config.max_attempts + 1):
            try:
                if sem:
                    await sem.acquire()
                try:
                    result = await self._resolver.invoke(
                        target.agent_id, input_data
                    )
                finally:
                    if sem:
                        await sem.release()

                if result.get("success"):
                    await self._circuit_breaker.record_success(target.agent_id)
                    return result, attempt
                raise RuntimeError(
                    f"Invocation returned success=false: {result.get('data')}"
                )
            except Exception as exc:
                last_error = exc
                await self._circuit_breaker.record_failure(target.agent_id)
                logger.warning(
                    "Attempt %d/%d failed for agent '%s': %s",
                    attempt,
                    recovery_config.max_attempts,
                    target.agent_id,
                    exc,
                )
                if attempt < recovery_config.max_attempts:
                    delay = recovery_config.backoff_base_seconds * (
                        2 ** (attempt - 1)
                    )
                    await asyncio.sleep(delay)

        logger.warning(
            "Agent '%s' exhausted %d retries: %s",
            target.agent_id,
            recovery_config.max_attempts,
            last_error,
        )
        return None, recovery_config.max_attempts

    @staticmethod
    def _build_fallback_query(
        original_ref: str | None, target: ResolvedTarget
    ) -> str | None:
        """Derive the search query for discovering alternative agents."""
        if original_ref and original_ref.startswith(SEARCH_PREFIX):
            return original_ref
        if target.description:
            return f"{SEARCH_PREFIX}{target.description}"
        if original_ref:
            return f"{SEARCH_PREFIX}{original_ref}"
        return None
