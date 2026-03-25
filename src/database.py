from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

import redis.asyncio as aioredis
from fastapi import Request
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.pool import NullPool

from src.core.settings import settings

if TYPE_CHECKING:
    from src.workflow.utils.background import BackgroundRunner

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Only echo in development
    poolclass=NullPool,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Alias used by workflow module
async_session_factory = AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Alias used by workflow module (auto-commits on success, rollbacks on error)
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> aioredis.Redis:
    """Return the Redis connection stored on the app state."""
    return request.app.state.redis


def get_background_runner(request: Request) -> BackgroundRunner:
    """Return the BackgroundRunner stored on the app state."""
    return request.app.state.background_runner
