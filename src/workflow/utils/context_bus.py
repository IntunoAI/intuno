"""Redis-backed context bus — scoped shared state per workflow execution.

Each execution gets a Redis hash at key ``ctx:{context_id}``.
Steps read/write named entries.  On execution completion the hash is given
a TTL so it doesn't linger forever.
"""


import json
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import Depends

from src.core.settings import settings
from src.database import get_redis


class ContextBus:
    def __init__(self, redis: aioredis.Redis = Depends(get_redis)) -> None:
        self._redis = redis

    def _key(self, context_id: uuid.UUID) -> str:
        return f"ctx:{context_id}"

    async def write(
        self, context_id: uuid.UUID, key: str, value: Any
    ) -> None:
        await self._redis.hset(self._key(context_id), key, json.dumps(value))

    async def read(self, context_id: uuid.UUID, key: str) -> Any | None:
        raw = await self._redis.hget(self._key(context_id), key)
        if raw is None:
            return None
        return json.loads(raw)

    async def snapshot(self, context_id: uuid.UUID) -> dict[str, Any]:
        raw_map = await self._redis.hgetall(self._key(context_id))
        return {k: json.loads(v) for k, v in raw_map.items()}

    async def finalize(self, context_id: uuid.UUID) -> None:
        """Set a TTL on the context hash so it auto-expires after completion."""
        await self._redis.expire(
            self._key(context_id), settings.WORKFLOW_CONTEXT_BUS_TTL_SECONDS
        )
