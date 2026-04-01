"""Redis-backed fixed-window rate limiting middleware.

Uses a simple fixed-window counter per client (by IP or authenticated user).
Gracefully degrades to allowing all requests when Redis is unavailable.
"""

import logging
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.core.settings import settings

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client rate limiter using Redis fixed-window counters."""

    async def dispatch(self, request: Request, call_next):
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/health/"):
            return await call_next(request)

        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            # Redis not available — allow request (graceful degradation)
            return await call_next(request)

        # Identify client: authenticated user or IP
        client_id = _get_client_id(request)
        window_seconds = 60
        now = int(time.time())
        window_key = f"rl:{client_id}:{now // window_seconds}"

        try:
            pipe = redis.pipeline(transaction=True)
            pipe.incr(window_key)
            pipe.expire(window_key, window_seconds + 1)
            results = await pipe.execute()
            count = results[0]

            limit = settings.RATE_LIMIT_REQUESTS_PER_MINUTE
            remaining = max(0, limit - count)
            retry_after = window_seconds - (now % window_seconds)

            if count > limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests"},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(now + retry_after),
                    },
                )

            response: Response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(now + retry_after)
            return response

        except Exception:
            # Redis error — allow request (graceful degradation)
            logger.debug("Rate limit check failed, allowing request", exc_info=True)
            return await call_next(request)


def _get_client_id(request: Request) -> str:
    """Extract a client identifier from the request."""
    # Check for authenticated user (set by auth middleware)
    user = getattr(request.state, "user_id", None)
    if user:
        return f"user:{user}"

    # Fall back to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host}" if request.client else "ip:unknown"
