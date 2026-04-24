"""Invite routes: public preview + redeem, admin CRUD.

Mounted at ``/invites``. Public endpoints validate the token itself;
admin endpoints require ``X-Service-Key``. No route accepts a normal
user JWT — invites pre-exist accounts.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import settings
from src.database import get_db
from src.exceptions import UnauthorizedException
from src.schemas.invite import (
    InviteCreate,
    InviteCreateResponse,
    InvitePreview,
    InviteRedeem,
    InviteRedeemResponse,
    InviteResponse,
)
from src.services.invite import (
    InviteEmailRequiredError,
    InviteEmailTakenError,
    InviteError,
    InviteExhaustedError,
    InviteExpiredError,
    InviteNotFoundError,
    InviteService,
    _build_url,
)

router = APIRouter(prefix="/invites", tags=["Invites"])


# ─── auth helper ───────────────────────────────────────────────────


async def require_service_key(
    x_service_key: Optional[str] = Header(default=None, alias="X-Service-Key"),
) -> None:
    """Reuse the service-key header for admin invite operations.

    We don't accept user JWTs here — inviting is an operator concern, not
    a user-facing one (yet). When a future referral UI lands, it can
    delegate via a separate route that does use user auth.
    """
    configured = settings.AGENTS_SERVICE_API_KEY
    if not configured or x_service_key != configured:
        raise UnauthorizedException("Invalid service key")


# ─── helpers ───────────────────────────────────────────────────────


def _map_invite_error_to_http(exc: InviteError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


# ─── public: preview + redeem ──────────────────────────────────────


@router.get("/{token}/preview", response_model=InvitePreview)
async def preview_invite(
    token: str,
    service: InviteService = Depends(),
) -> InvitePreview:
    try:
        invite = await service.preview(token)
    except (InviteNotFoundError, InviteExpiredError, InviteExhaustedError) as exc:
        raise _map_invite_error_to_http(exc) from exc

    inviter_name = await service.resolve_inviter_name(invite)
    return InvitePreview(
        email=invite.email,
        inviter_name=inviter_name,
        expires_at=invite.expires_at,
        max_uses=invite.max_uses,
        use_count=invite.use_count,
    )


@router.post(
    "/{token}/redeem",
    response_model=InviteRedeemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def redeem_invite(
    token: str,
    body: InviteRedeem,
    service: InviteService = Depends(),
) -> InviteRedeemResponse:
    try:
        jwt = await service.redeem(token, body)
    except InviteError as exc:
        raise _map_invite_error_to_http(exc) from exc

    return InviteRedeemResponse(access_token=jwt)


# ─── admin: create / list / delete ─────────────────────────────────


@router.post(
    "",
    response_model=InviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invite(
    data: InviteCreate,
    _: None = Depends(require_service_key),
    service: InviteService = Depends(),
) -> InviteCreateResponse:
    invite, url = await service.create_invite(data)
    return InviteCreateResponse(
        id=invite.id,
        token=invite.token,
        expires_at=invite.expires_at,
        url=url,
    )


@router.get("", response_model=List[InviteResponse])
async def list_invites(
    _: None = Depends(require_service_key),
    unredeemed_only: bool = False,
    include_expired: bool = True,
    service: InviteService = Depends(),
) -> List[InviteResponse]:
    rows = await service.list_invites(
        unredeemed_only=unredeemed_only,
        include_expired=include_expired,
    )
    return [InviteResponse.model_validate(r) for r in rows]


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(
    invite_id: UUID,
    _: None = Depends(require_service_key),
    service: InviteService = Depends(),
) -> None:
    ok = await service.delete_invite(invite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Invite not found")
