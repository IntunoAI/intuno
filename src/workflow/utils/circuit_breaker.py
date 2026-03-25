"""Circuit breaker — track agent failure rates and prevent routing to degraded agents.

Uses Redis sorted sets for windowed failure counting and string keys for
state tracking.  The state machine follows the standard pattern:

    closed    ->  (threshold exceeded in window)   ->  open
    open      ->  (cooldown elapsed)               ->  half_open
    half_open -> (probe succeeds)                  ->  closed
    half_open -> (probe fails)                     ->  open

System-level defaults live in ``Settings``.  Per-workflow overrides can be
passed via ``CircuitBreakerConfig`` in the DSL — they are applied at
construction time through the ``from_config`` class method.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
from fastapi import Depends

from src.core.settings import settings
from src.database import get_redis

if TYPE_CHECKING:
    from src.workflow.models.dsl import CircuitBreakerConfig

logger = logging.getLogger(__name__)

STATE_CLOSED = "closed"
STATE_OPEN = "open"
STATE_HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        redis: aioredis.Redis = Depends(get_redis),
        failure_threshold: int | None = None,
        window_seconds: int | None = None,
        cooldown_seconds: int | None = None,
    ) -> None:
        self._redis = redis
        self._failure_threshold = (
            failure_threshold or settings.WORKFLOW_CIRCUIT_BREAKER_FAILURE_THRESHOLD
        )
        self._window_seconds = (
            window_seconds or settings.WORKFLOW_CIRCUIT_BREAKER_WINDOW_SECONDS
        )
        self._cooldown_seconds = (
            cooldown_seconds or settings.WORKFLOW_CIRCUIT_BREAKER_COOLDOWN_SECONDS
        )

    @classmethod
    def from_config(
        cls,
        redis: aioredis.Redis,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Create a breaker with optional per-workflow overrides."""
        if config is None:
            return cls(redis)
        return cls(
            redis,
            failure_threshold=config.failure_threshold,
            window_seconds=config.window_seconds,
            cooldown_seconds=config.cooldown_seconds,
        )

    def _key(self, agent_id: str, suffix: str) -> str:
        return f"cb:{agent_id}:{suffix}"

    async def is_available(self, agent_id: str) -> bool:
        """Return True if the agent can be invoked (closed or half-open probe)."""
        state = await self._get_state(agent_id)

        if state == STATE_CLOSED:
            return True

        if state == STATE_OPEN:
            opened_at = await self._redis.get(self._key(agent_id, "opened_at"))
            if opened_at is not None:
                elapsed = time.time() - float(opened_at)
                if elapsed >= self._cooldown_seconds:
                    await self._set_state(agent_id, STATE_HALF_OPEN)
                    logger.info(
                        "Circuit breaker for '%s' moved to half-open "
                        "(cooldown %.0fs elapsed)",
                        agent_id,
                        elapsed,
                    )
                    return True
            return False

        if state == STATE_HALF_OPEN:
            return True

        return True

    async def record_success(self, agent_id: str) -> None:
        """Record a successful invocation.  Closes the breaker if half-open."""
        state = await self._get_state(agent_id)
        if state == STATE_HALF_OPEN:
            logger.info(
                "Circuit breaker for '%s' closing (half-open probe succeeded)",
                agent_id,
            )
            await self._set_state(agent_id, STATE_CLOSED)
            await self._redis.delete(
                self._key(agent_id, "failures"),
                self._key(agent_id, "opened_at"),
            )

    async def record_failure(self, agent_id: str) -> None:
        """Record a failed invocation.  Opens the breaker if threshold exceeded."""
        state = await self._get_state(agent_id)

        if state == STATE_HALF_OPEN:
            logger.warning(
                "Circuit breaker for '%s' re-opening (half-open probe failed)",
                agent_id,
            )
            await self._open(agent_id)
            return

        now = time.time()
        failures_key = self._key(agent_id, "failures")

        await self._redis.zadd(failures_key, {str(now): now})

        cutoff = now - self._window_seconds
        await self._redis.zremrangebyscore(failures_key, "-inf", cutoff)

        count = await self._redis.zcard(failures_key)

        if count >= self._failure_threshold:
            logger.warning(
                "Circuit breaker for '%s' tripped: %d failures in %ds window",
                agent_id,
                count,
                self._window_seconds,
            )
            await self._open(agent_id)

    async def get_state(self, agent_id: str) -> str:
        """Public accessor for the current breaker state."""
        return await self._get_state(agent_id)

    async def _get_state(self, agent_id: str) -> str:
        raw = await self._redis.get(self._key(agent_id, "state"))
        if raw is None:
            return STATE_CLOSED
        return raw if isinstance(raw, str) else raw.decode()

    async def _set_state(self, agent_id: str, state: str) -> None:
        await self._redis.set(self._key(agent_id, "state"), state)

    async def _open(self, agent_id: str) -> None:
        await self._set_state(agent_id, STATE_OPEN)
        await self._redis.set(
            self._key(agent_id, "opened_at"), str(time.time())
        )
