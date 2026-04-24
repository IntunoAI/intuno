"""Pydantic schemas for user_invites."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class InviteCreate(BaseModel):
    """Admin creates an invite. All fields optional except when behavior matters."""

    email: Optional[EmailStr] = None
    note: Optional[str] = Field(default=None, max_length=255)
    expires_at: Optional[datetime] = None
    max_uses: int = Field(default=1, ge=1, le=10_000)


class InvitePreview(BaseModel):
    """Public preview of an invite — returned by GET /invites/{token}/preview."""

    email: Optional[EmailStr] = None
    inviter_name: Optional[str] = None
    expires_at: Optional[datetime] = None
    max_uses: int
    use_count: int


class InviteRedeem(BaseModel):
    """Body for POST /invites/{token}/redeem.

    ``email`` may be provided when the invite is not email-locked. If the
    invite has an email set, the request's email must match or be omitted.
    """

    email: Optional[EmailStr] = None
    password: str = Field(..., min_length=6, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=64)
    last_name: Optional[str] = Field(default=None, max_length=64)


class InviteResponse(BaseModel):
    """Admin-facing invite row."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    token: str
    email: Optional[EmailStr]
    inviter_user_id: Optional[UUID]
    note: Optional[str]
    redeemed_at: Optional[datetime]
    redeemed_by_user_id: Optional[UUID]
    expires_at: Optional[datetime]
    max_uses: int
    use_count: int
    created_at: datetime


class InviteCreateResponse(BaseModel):
    """Returned from POST /invites — includes the share-ready URL."""

    id: UUID
    token: str
    expires_at: Optional[datetime]
    url: str  # e.g. https://intuno.net/personal/invite?token=…


class InviteRedeemResponse(BaseModel):
    """Returned from POST /invites/{token}/redeem — logs the user in."""

    access_token: str
    token_type: str = "bearer"
