"""Redis-based concurrency limiter for agent invocations and workflow executions.

Uses Redis INCR/DECR with a TTL safety net so counters self-heal if a
process crashes without releasing.  Two scopes:

- **per-agent**: caps concurrent invocations of a single agent across all
  workflows (key ``conc:agent:{agent_id}``).
- **per-workflow**: caps concurrent executions of a single workflow
  definition (key ``conc:wf:{workflow_id}``).

Slot availability is communicated via Redis pub/sub so waiters wake up
immediately instead of polling.
"""

import asyncio
import logging
import uuid

import redis.asyncio as aioredis
from fastapi import Depends

from src.core.settings import settings
from src.database import get_redis

logger = logging.getLogger(__name__)

_SAFETY_TTL = 600  # auto-expire counters after 10 min of inactivity


class ConcurrencyLimitExceeded(Exception):
    """Raised when a semaphore cannot be acquired within the allowed wait."""


class RedisSemaphore:
    """Counting semaphore backed by a Redis key (INCR/DECR).

    Uses pub/sub notifications on release so waiters don't have to poll.
    Falls back to a short polling interval if pub/sub subscription fails.
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        key: str,
        limit: int,
        poll_interval: float = 0.25,
        timeout: float = 30.0,
    ) -> None:
        self._redis = redis
        self._key = key
        self._limit = limit
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._notify_channel = f"conc:notify:{key}"

    async def acquire(self) -> None:
        # Try to acquire immediately
        current = await self._redis.incr(self._key)
        await self._redis.expire(self._key, _SAFETY_TTL)
        if current <= self._limit:
            return
        await self._redis.decr(self._key)

        # Slot not available — wait for a pub/sub notification
        deadline = asyncio.get_event_loop().time() + self._timeout

        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(self._notify_channel)
        except Exception:
            # Pub/sub failed — fall back to polling
            logger.debug(
                "Pub/sub subscribe failed for %s, falling back to polling", self._key
            )
            await self._acquire_poll(deadline)
            return

        try:
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise ConcurrencyLimitExceeded(
                        f"Concurrency limit ({self._limit}) for '{self._key}' "
                        f"not released within {self._timeout}s"
                    )

                # Wait for notification with timeout
                try:
                    await asyncio.wait_for(
                        pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=remaining
                        ),
                        timeout=min(remaining, self._poll_interval * 4),
                    )
                except asyncio.TimeoutError:
                    pass

                # Try to acquire regardless of whether we got a message
                # (handles race conditions and missed notifications)
                current = await self._redis.incr(self._key)
                await self._redis.expire(self._key, _SAFETY_TTL)
                if current <= self._limit:
                    return
                await self._redis.decr(self._key)
        finally:
            await pubsub.unsubscribe(self._notify_channel)
            await pubsub.aclose()

    async def _acquire_poll(self, deadline: float) -> None:
        """Fallback polling loop when pub/sub is unavailable."""
        while True:
            current = await self._redis.incr(self._key)
            await self._redis.expire(self._key, _SAFETY_TTL)
            if current <= self._limit:
                return
            await self._redis.decr(self._key)
            if asyncio.get_event_loop().time() >= deadline:
                raise ConcurrencyLimitExceeded(
                    f"Concurrency limit ({self._limit}) for '{self._key}' "
                    f"not released within {self._timeout}s"
                )
            await asyncio.sleep(self._poll_interval)

    async def release(self) -> None:
        val = await self._redis.decr(self._key)
        if val < 0:
            await self._redis.set(self._key, 0)
        # Notify waiters that a slot is available
        try:
            await self._redis.publish(self._notify_channel, "released")
        except Exception:
            pass  # Best-effort notification; waiters will retry on timeout


class ConcurrencyLimiter:
    """High-level API used by the orchestrator and recovery manager."""

    def __init__(self, redis: aioredis.Redis = Depends(get_redis)) -> None:
        self._redis = redis

    def agent_semaphore(
        self,
        agent_id: str,
        limit: int | None = None,
    ) -> RedisSemaphore:
        effective = limit or settings.WORKFLOW_DEFAULT_MAX_CONCURRENT_PER_AGENT
        return RedisSemaphore(self._redis, f"conc:agent:{agent_id}", effective)

    def workflow_semaphore(
        self,
        workflow_id: uuid.UUID,
        limit: int | None = None,
    ) -> RedisSemaphore:
        effective = limit or settings.WORKFLOW_DEFAULT_MAX_CONCURRENT_EXECUTIONS
        return RedisSemaphore(self._redis, f"conc:wf:{workflow_id}", effective)
