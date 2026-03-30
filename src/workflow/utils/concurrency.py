"""Redis-based concurrency limiter for agent invocations and workflow executions.

Uses Redis INCR/DECR with a TTL safety net so counters self-heal if a
process crashes without releasing.  Two scopes:

- **per-agent**: caps concurrent invocations of a single agent across all
  workflows (key ``conc:agent:{agent_id}``).
- **per-workflow**: caps concurrent executions of a single workflow
  definition (key ``conc:wf:{workflow_id}``).
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
    """Counting semaphore backed by a Redis key (INCR/DECR)."""

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

    async def acquire(self) -> None:
        deadline = asyncio.get_event_loop().time() + self._timeout
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


class ConcurrencyLimiter:
    """High-level API used by the orchestrator and recovery manager."""

    def __init__(self, redis: aioredis.Redis = Depends(get_redis)) -> None:
        self._redis = redis

    def agent_semaphore(
        self, agent_id: str, limit: int | None = None,
    ) -> RedisSemaphore:
        effective = limit or settings.WORKFLOW_DEFAULT_MAX_CONCURRENT_PER_AGENT
        return RedisSemaphore(self._redis, f"conc:agent:{agent_id}", effective)

    def workflow_semaphore(
        self, workflow_id: uuid.UUID, limit: int | None = None,
    ) -> RedisSemaphore:
        effective = limit or settings.WORKFLOW_DEFAULT_MAX_CONCURRENT_EXECUTIONS
        return RedisSemaphore(self._redis, f"conc:wf:{workflow_id}", effective)
