"""Redis client for caching. Optional: if REDIS_URL is empty, operations no-op."""

import json
import logging
from typing import Any, Optional

from redis.asyncio import Redis

from src.core.settings import settings

logger = logging.getLogger(__name__)

_redis: Optional[Redis] = None


async def get_redis() -> Optional[Redis]:
    """Get Redis client. Returns None if Redis is not configured."""
    return _redis


async def init_redis() -> None:
    """Initialize Redis connection. No-op if REDIS_URL is empty."""
    global _redis
    if not settings.REDIS_URL or settings.REDIS_URL.strip() == "":
        logger.info("Redis URL not set; caching disabled")
        return
    try:
        _redis = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await _redis.ping()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed: %s; caching disabled", e)
        _redis = None


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        logger.info("Redis disconnected")


async def cache_get(key: str) -> Optional[Any]:
    """Get value from cache. Returns None if not found or Redis unavailable."""
    client = await get_redis()
    if not client:
        return None
    try:
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:
        logger.warning("Cache get failed for %s: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> bool:
    """Set value in cache. Returns False if Redis unavailable."""
    client = await get_redis()
    if not client:
        return False
    try:
        raw = json.dumps(value)
        await client.set(key, raw, ex=ttl_seconds)
        return True
    except Exception as e:
        logger.warning("Cache set failed for %s: %s", key, e)
        return False
