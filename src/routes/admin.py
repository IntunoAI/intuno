"""Admin routes — platform governance and agent kill switch.

All endpoints require admin privileges via the get_admin_user dependency.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.admin_auth import get_admin_user
from src.database import get_db
from src.exceptions import NotFoundException
from src.models.auth import User
from src.models.registry import Agent
from src.services import safety

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Request/Response schemas ────────────────────────────────────────


class KillAgentRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Why is this agent being disabled?")


class HaltPlatformRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Why is the platform being halted?")


class AgentStatusResponse(BaseModel):
    agent_id: str
    agent_uuid: UUID
    name: str
    is_active: bool
    owner_id: UUID


class PlatformStatusResponse(BaseModel):
    halted: bool
    reason: Optional[str] = None
    halted_by: Optional[str] = None
    redis_available: bool
    disabled_agent_count: int = 0


# ── Agent kill switch ───────────────────────────────────────────────


@router.post("/agents/{agent_uuid}/kill")
async def kill_agent(
    agent_uuid: UUID,
    body: KillAgentRequest,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Force-disable an agent. Sets is_active=False and caches in Redis."""
    result = await session.execute(select(Agent).where(Agent.id == agent_uuid))
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundException("Agent")

    agent.is_active = False
    await session.commit()

    # Cache kill in Redis for fast rejection
    await safety.kill_agent(agent_uuid)

    return {
        "success": True,
        "agent_id": agent.agent_id,
        "agent_uuid": str(agent_uuid),
        "reason": body.reason,
        "killed_by": str(admin.id),
    }


@router.post("/agents/{agent_uuid}/reactivate")
async def reactivate_agent(
    agent_uuid: UUID,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Re-enable a previously disabled agent."""
    result = await session.execute(select(Agent).where(Agent.id == agent_uuid))
    agent = result.scalar_one_or_none()
    if not agent:
        raise NotFoundException("Agent")

    agent.is_active = True
    await session.commit()

    # Clear Redis kill cache
    await safety.reactivate_agent(agent_uuid)

    return {
        "success": True,
        "agent_id": agent.agent_id,
        "agent_uuid": str(agent_uuid),
        "reactivated_by": str(admin.id),
    }


@router.get("/agents/disabled", response_model=list[AgentStatusResponse])
async def list_disabled_agents(
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """List all currently disabled agents."""
    result = await session.execute(
        select(Agent).where(Agent.is_active == False).order_by(Agent.updated_at.desc())  # noqa: E712
    )
    agents = result.scalars().all()

    return [
        AgentStatusResponse(
            agent_id=a.agent_id,
            agent_uuid=a.id,
            name=a.name,
            is_active=a.is_active,
            owner_id=a.user_id,
        )
        for a in agents
    ]


# ── Platform halt ───────────────────────────────────────────────────


@router.post("/platform/halt")
async def halt_platform(
    body: HaltPlatformRequest,
    admin: User = Depends(get_admin_user),
):
    """Emergency halt — suspend all agent operations platform-wide."""
    await safety.halt_platform(body.reason, admin.id)
    return {
        "success": True,
        "halted": True,
        "reason": body.reason,
        "halted_by": str(admin.id),
    }


@router.post("/platform/resume")
async def resume_platform(
    admin: User = Depends(get_admin_user),
):
    """Resume platform operations after an emergency halt."""
    await safety.resume_platform(admin.id)
    return {
        "success": True,
        "halted": False,
        "resumed_by": str(admin.id),
    }


@router.get("/platform/status", response_model=PlatformStatusResponse)
async def get_platform_status(
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Get current platform safety status."""
    status = await safety.get_platform_status()

    # Count disabled agents
    result = await session.execute(
        select(func.count()).select_from(Agent).where(Agent.is_active == False)  # noqa: E712
    )
    disabled_count = result.scalar() or 0

    return PlatformStatusResponse(
        halted=status.get("halted", False),
        reason=status.get("reason"),
        halted_by=status.get("halted_by"),
        redis_available=status.get("redis_available", False),
        disabled_agent_count=disabled_count,
    )
