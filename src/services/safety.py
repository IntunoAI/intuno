"""Safety service — platform halt, agent kill switch, and safety checks.

Provides the central "off switch" for the Intuno platform. All communication
chokepoints (broker, channels, A2A) call into this service before processing.
"""

import logging
from typing import Optional
from uuid import UUID

from src.core.redis_client import get_redis
from src.core.settings import settings
from src.exceptions import AgentDisabledException, PlatformHaltedException

logger = logging.getLogger(__name__)

# Redis key constants
EMERGENCY_HALT_KEY = "platform:emergency_halt"
EMERGENCY_HALT_REASON_KEY = "platform:emergency_halt:reason"
EMERGENCY_HALT_ACTOR_KEY = "platform:emergency_halt:actor"
AGENT_STATUS_PREFIX = "agent:status:"


async def check_platform_halt() -> None:
    """Raise PlatformHaltedException if the platform is in emergency halt.

    This is designed to be called at every communication chokepoint.
    Fast O(1) Redis GET — adds ~0.1ms overhead per call.
    Fails open if Redis is unavailable (consistent with rate limiter pattern).
    """
    if not settings.SAFETY_CHECK_ENABLED:
        return

    redis = await get_redis()
    if not redis:
        return  # Fail open: if Redis is down, allow requests

    try:
        halted = await redis.get(EMERGENCY_HALT_KEY)
        if halted == "1":
            reason = await redis.get(EMERGENCY_HALT_REASON_KEY)
            detail = "Platform is in emergency halt mode."
            if reason:
                detail += f" Reason: {reason}"
            raise PlatformHaltedException(detail)
    except PlatformHaltedException:
        raise
    except Exception as e:
        logger.warning("Safety check (platform halt) failed: %s", e)


async def check_agent_active(agent_id: UUID) -> None:
    """Raise AgentDisabledException if the agent has been killed/deactivated.

    Checks Redis cache first, falls back to no-op if unavailable.
    The authoritative is_active check remains in the broker/service layer
    via the DB — this adds a fast-path rejection for killed agents.
    """
    if not settings.SAFETY_CHECK_ENABLED:
        return

    redis = await get_redis()
    if not redis:
        return  # Fail open

    try:
        key = f"{AGENT_STATUS_PREFIX}{agent_id}"
        cached = await redis.get(key)
        if cached == "0":
            raise AgentDisabledException()
    except AgentDisabledException:
        raise
    except Exception as e:
        logger.warning("Safety check (agent status) failed: %s", e)


async def halt_platform(reason: str, actor_id: UUID) -> None:
    """Activate emergency halt — all agent operations will be rejected."""
    redis = await get_redis()
    if not redis:
        raise RuntimeError("Redis is required for platform halt")

    await redis.set(EMERGENCY_HALT_KEY, "1")
    await redis.set(EMERGENCY_HALT_REASON_KEY, reason)
    await redis.set(EMERGENCY_HALT_ACTOR_KEY, str(actor_id))
    logger.critical(
        "PLATFORM HALT activated by user %s. Reason: %s",
        actor_id,
        reason,
    )


async def resume_platform(actor_id: UUID) -> None:
    """Deactivate emergency halt — resume normal operations."""
    redis = await get_redis()
    if not redis:
        raise RuntimeError("Redis is required for platform resume")

    await redis.delete(EMERGENCY_HALT_KEY)
    await redis.delete(EMERGENCY_HALT_REASON_KEY)
    await redis.delete(EMERGENCY_HALT_ACTOR_KEY)
    logger.critical("PLATFORM HALT deactivated by user %s", actor_id)


async def kill_agent(agent_id: UUID) -> None:
    """Cache agent as killed in Redis for fast rejection at chokepoints."""
    redis = await get_redis()
    if not redis:
        return

    key = f"{AGENT_STATUS_PREFIX}{agent_id}"
    await redis.set(key, "0", ex=settings.AGENT_STATUS_CACHE_TTL)
    logger.warning("Agent %s killed (cached in Redis)", agent_id)


async def reactivate_agent(agent_id: UUID) -> None:
    """Remove killed status from Redis cache."""
    redis = await get_redis()
    if not redis:
        return

    key = f"{AGENT_STATUS_PREFIX}{agent_id}"
    await redis.delete(key)
    logger.info("Agent %s reactivated (Redis cache cleared)", agent_id)


async def get_platform_status() -> dict:
    """Get current platform safety status."""
    redis = await get_redis()
    if not redis:
        return {"halted": False, "redis_available": False}

    try:
        halted = await redis.get(EMERGENCY_HALT_KEY)
        reason = await redis.get(EMERGENCY_HALT_REASON_KEY)
        actor = await redis.get(EMERGENCY_HALT_ACTOR_KEY)
        return {
            "halted": halted == "1",
            "reason": reason,
            "halted_by": actor,
            "redis_available": True,
        }
    except Exception as e:
        logger.warning("Failed to get platform status: %s", e)
        return {"halted": False, "redis_available": False, "error": str(e)}
