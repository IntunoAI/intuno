"""Safety routes — public halt endpoint and admin halt code management.

The halt endpoint is intentionally PUBLIC (no JWT required). The code
itself is the authentication. This is by design: it should be easy to
stop the platform, harder to restart it.
"""

import secrets
from typing import Optional
from uuid import UUID

import bcrypt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.admin_auth import get_admin_user
from src.database import get_db
from src.models.auth import User
from src.models.halt_code import HaltCode
from src.services import safety

router = APIRouter(prefix="/safety", tags=["Safety"])


# ── Schemas ─────────────────────────────────────────────────────────


class HaltRequest(BaseModel):
    code: str = Field(..., min_length=1, description="Halt code issued to a trustee")
    reason: Optional[str] = Field(default=None, description="Optional reason for halting")


class HaltResponse(BaseModel):
    halted: bool
    trustee: str
    reason: Optional[str] = None
    message: str


class CreateHaltCodeRequest(BaseModel):
    trustee_name: str = Field(..., min_length=1)
    trustee_email: Optional[str] = None
    label: str = Field(..., min_length=1, description="Human-readable label, e.g. 'Guardian - Europe'")
    is_master: bool = Field(default=False)


class CreateHaltCodeResponse(BaseModel):
    id: UUID
    label: str
    trustee_name: str
    is_master: bool
    code: str = Field(description="The plaintext code — shown ONCE, never stored")


class HaltCodeListItem(BaseModel):
    id: UUID
    label: str
    trustee_name: str
    trustee_email: Optional[str]
    is_master: bool
    is_active: bool


class PlatformStatusPublic(BaseModel):
    halted: bool
    message: str


# ── Public endpoints (no auth) ──────────────────────────────────────


@router.get("/status", response_model=PlatformStatusPublic)
async def get_public_status():
    """Public platform status — anyone can check if the platform is halted."""
    status = await safety.get_platform_status()
    halted = status.get("halted", False)
    return PlatformStatusPublic(
        halted=halted,
        message="Platform is halted. All agent operations are suspended." if halted
        else "Platform is operational.",
    )


@router.post("/halt", response_model=HaltResponse)
async def halt_with_code(
    body: HaltRequest,
    session: AsyncSession = Depends(get_db),
):
    """Halt the platform using a trustee code.

    This endpoint is PUBLIC — no JWT required. The halt code is the
    authentication. By design, stopping the platform should be easy.
    Restarting requires admin authentication.
    """
    # Find all active halt codes and check against each
    result = await session.execute(
        select(HaltCode).where(HaltCode.is_active == True)  # noqa: E712
    )
    halt_codes = result.scalars().all()

    matched_code = None
    for hc in halt_codes:
        if bcrypt.checkpw(body.code.encode("utf-8"), hc.code_hash.encode("utf-8")):
            matched_code = hc
            break

    if not matched_code:
        from src.exceptions import ForbiddenException
        raise ForbiddenException("Invalid halt code")

    reason = body.reason or f"Halted by trustee: {matched_code.trustee_name}"
    await safety.halt_platform(reason, matched_code.created_by)

    return HaltResponse(
        halted=True,
        trustee=matched_code.trustee_name,
        reason=reason,
        message="Platform has been halted. All agent operations are suspended.",
    )


# ── Admin endpoints (manage halt codes) ─────────────────────────────


@router.post("/codes", response_model=CreateHaltCodeResponse)
async def create_halt_code(
    body: CreateHaltCodeRequest,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a new halt code for a trustee. The plaintext code is returned
    ONCE and never stored — only its bcrypt hash is persisted."""
    # Generate a secure random code: 8 groups of 4 chars
    raw_code = "-".join(
        secrets.token_hex(2).upper() for _ in range(4)
    )

    code_hash = bcrypt.hashpw(
        raw_code.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    halt_code = HaltCode(
        code_hash=code_hash,
        label=body.label,
        trustee_name=body.trustee_name,
        trustee_email=body.trustee_email,
        is_master=body.is_master,
        created_by=admin.id,
    )
    session.add(halt_code)
    await session.commit()
    await session.refresh(halt_code)

    return CreateHaltCodeResponse(
        id=halt_code.id,
        label=body.label,
        trustee_name=body.trustee_name,
        is_master=body.is_master,
        code=raw_code,
    )


@router.get("/codes", response_model=list[HaltCodeListItem])
async def list_halt_codes(
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """List all halt codes (without the actual codes — those are never stored)."""
    result = await session.execute(
        select(HaltCode).order_by(HaltCode.created_at.desc())
    )
    codes = result.scalars().all()
    return [
        HaltCodeListItem(
            id=c.id,
            label=c.label,
            trustee_name=c.trustee_name,
            trustee_email=c.trustee_email,
            is_master=c.is_master,
            is_active=c.is_active,
        )
        for c in codes
    ]


@router.delete("/codes/{code_id}")
async def revoke_halt_code(
    code_id: UUID,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Revoke a halt code — it can no longer be used to halt the platform."""
    result = await session.execute(select(HaltCode).where(HaltCode.id == code_id))
    halt_code = result.scalar_one_or_none()
    if not halt_code:
        from src.exceptions import NotFoundException
        raise NotFoundException("Halt code")

    halt_code.is_active = False
    await session.commit()

    return {"success": True, "revoked": str(code_id)}
