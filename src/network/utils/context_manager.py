"""Network-scoped context manager.

Maintains a fast Redis cache of recent messages per network alongside
the authoritative Postgres storage.  When delivering a message to an
external agent, we build a context window from Redis for low-latency.
"""

import json
import time
import uuid
from typing import Any

import redis.asyncio as aioredis
from fastapi import Depends

from src.core.settings import settings
from src.database import get_redis


class NetworkContextManager:
    """Redis-backed context accumulator for communication networks."""

    def __init__(self, redis: aioredis.Redis = Depends(get_redis)) -> None:
        self._redis = redis

    def _stream_key(self, network_id: uuid.UUID) -> str:
        return f"net:{network_id}:ctx"

    async def append(
        self,
        network_id: uuid.UUID,
        *,
        sender: str,
        recipient: str | None,
        channel: str,
        content: str,
        message_id: uuid.UUID | None = None,
    ) -> None:
        """Append a message to the network context stream."""
        entry = {
            "sender": sender,
            "recipient": recipient or "",
            "channel": channel,
            "content": content,
            "message_id": str(message_id) if message_id else "",
            "ts": str(time.time()),
        }
        key = self._stream_key(network_id)
        await self._redis.xadd(key, entry, maxlen=settings.NETWORK_CONTEXT_MAX_ENTRIES)
        await self._redis.expire(key, settings.NETWORK_CONTEXT_TTL_SECONDS)

    async def get_context_window(
        self,
        network_id: uuid.UUID,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve recent context entries from Redis stream."""
        key = self._stream_key(network_id)
        # Read from the end of the stream
        entries = await self._redis.xrevrange(key, count=limit)
        result = []
        for _stream_id, data in reversed(entries):
            result.append(
                {
                    "sender": data["sender"],
                    "recipient": data["recipient"] or None,
                    "channel": data["channel"],
                    "content": data["content"],
                    "timestamp": float(data["ts"]),
                }
            )
        return result

    async def clear(self, network_id: uuid.UUID) -> None:
        """Delete the context stream for a network."""
        await self._redis.delete(self._stream_key(network_id))
