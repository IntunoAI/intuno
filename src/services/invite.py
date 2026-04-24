"""Invite service — business logic for /invites preview + redeem + admin CRUD.

Keeps repository calls + cross-service orchestration (user creation,
JWT issuance) in one place so the route layer stays thin.
"""

import secrets
from datetime import datetime, timezone
from typing import Optional, Tuple
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import settings
from src.database import get_db
from src.models.user_invite import UserInvite
from src.repositories.invite import InviteRepository
from src.schemas.auth import UserRegister
from src.schemas.invite import InviteCreate, InviteRedeem
from src.services.auth import AuthService


class InviteError(ValueError):
    """Base for redeem-flow failures that map to specific HTTP codes."""

    status_code: int = 400


class InviteNotFoundError(InviteError):
    status_code = 404


class InviteExpiredError(InviteError):
    status_code = 410


class InviteExhaustedError(InviteError):
    status_code = 410


class InviteEmailMismatchError(InviteError):
    status_code = 400


class InviteEmailTakenError(InviteError):
    status_code = 409


def _gen_token() -> str:
    """URL-safe random token; ~43 chars."""
    return secrets.token_urlsafe(32)


def _build_url(token: str) -> str:
    """Assemble the public invite URL using the frontend origin.

    wisdom's ``BASE_URL`` points at the API; the frontend lives elsewhere.
    We fall back to the API host for now; swap to a dedicated
    ``FRONTEND_BASE_URL`` once that lands in settings.
    """
    base = getattr(settings, "FRONTEND_BASE_URL", None) or settings.BASE_URL
    base = base.rstrip("/")
    return f"{base}/personal/invite?token={token}"


class InviteService:
    def __init__(
        self,
        session: AsyncSession = Depends(get_db),
        invite_repo: InviteRepository = Depends(),
        auth_service: AuthService = Depends(),
    ):
        self.session = session
        self.invite_repo = invite_repo
        self.auth_service = auth_service

    # ─── create / list / delete (admin) ────────────────────────────

    async def create_invite(
        self,
        data: InviteCreate,
        inviter_user_id: Optional[UUID] = None,
    ) -> Tuple[UserInvite, str]:
        """Create an invite with a fresh token. Returns (invite, share_url)."""
        invite = UserInvite(
            token=_gen_token(),
            email=data.email,
            note=data.note,
            expires_at=data.expires_at,
            max_uses=data.max_uses,
            inviter_user_id=inviter_user_id,
            use_count=0,
        )
        saved = await self.invite_repo.create(invite)
        return saved, _build_url(saved.token)

    async def list_invites(
        self, *, unredeemed_only: bool = False, include_expired: bool = True
    ):
        return await self.invite_repo.list(
            unredeemed_only=unredeemed_only,
            include_expired=include_expired,
        )

    async def delete_invite(self, invite_id: UUID) -> bool:
        return await self.invite_repo.delete(invite_id)

    # ─── preview (public) ──────────────────────────────────────────

    async def preview(self, token: str) -> UserInvite:
        """Return the invite for preview, raising specific errors for UX."""
        invite = await self.invite_repo.get_by_token(token)
        if invite is None:
            raise InviteNotFoundError(f"Invite '{token[:8]}…' not found")
        _ensure_available(invite)
        return invite

    async def resolve_inviter_name(self, invite: UserInvite) -> Optional[str]:
        """Fetch the inviter's display name (best-effort, may return None)."""
        if invite.inviter_user_id is None:
            return None
        user = await self.auth_service.get_user_by_id(invite.inviter_user_id)
        if user is None:
            return None
        if user.first_name:
            return user.first_name
        return user.email

    # ─── redeem (public) ───────────────────────────────────────────

    async def redeem(self, token: str, body: InviteRedeem) -> str:
        """Redeem an invite: validate → create user → mark redeemed.

        Returns a fresh JWT. Raises InviteError subclasses on any
        validation failure; caller maps to HTTP status via
        ``.status_code``.
        """
        invite = await self.invite_repo.get_by_token(token)
        if invite is None:
            raise InviteNotFoundError(f"Invite '{token[:8]}…' not found")
        _ensure_available(invite)

        # Decide the final email: invite-locked beats body.email
        final_email: Optional[str]
        if invite.email is not None:
            if body.email and body.email.lower() != invite.email.lower():
                raise InviteEmailMismatchError(
                    "This invite is locked to a specific email address"
                )
            final_email = invite.email
        else:
            if not body.email:
                raise InviteEmailMismatchError(
                    "Email is required for invites that aren't pre-locked"
                )
            final_email = body.email

        # Create user via the existing auth flow. register_user raises
        # ValueError("User with this email already exists") which we map
        # to a specific 409 for the API.
        try:
            user = await self.auth_service.register_user(
                UserRegister(
                    email=final_email,
                    password=body.password,
                    first_name=body.first_name,
                    last_name=body.last_name,
                )
            )
        except ValueError as exc:
            if "already exists" in str(exc).lower():
                raise InviteEmailTakenError(
                    "An account already exists for this email"
                ) from exc
            raise

        # Mark the invite redeemed — atomic update + use_count bump
        updated = await self.invite_repo.mark_redeemed(invite.id, user.id)
        if updated is None:
            # Should never happen — row disappeared between lookup and commit.
            raise InviteNotFoundError("Invite disappeared during redemption")

        return self.auth_service.create_access_token(user.id)


# ─── helpers ───────────────────────────────────────────────────────


def _ensure_available(invite: UserInvite) -> None:
    """Raise if the invite is expired or fully consumed."""
    now = datetime.now(tz=timezone.utc)
    if invite.expires_at is not None and invite.expires_at < now:
        raise InviteExpiredError("This invite has expired")
    if invite.use_count >= invite.max_uses:
        raise InviteExhaustedError("This invite has already been used")
