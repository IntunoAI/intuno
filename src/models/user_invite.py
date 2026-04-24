"""User-invite model — gates signup to /personal during early access.

Each row is a single token a prospective user can redeem to create an
account. Tokens may be single- or multi-use, optionally email-locked,
and optionally time-bounded. Operators create invites via the HTTP
API (service-key auth) or the CLI.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from src.models.base import Base
import uuid


class UserInvite(Base):
    """An invitation token."""

    __tablename__ = "user_invites"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # The URL-safe token string (the "shareable secret"); unique index.
    token = Column(String(64), unique=True, nullable=False, index=True)

    # Optional pre-filled email. When set, redemption must use this email
    # (tokens email-locked to a specific address). When null, any email
    # works on redemption.
    email = Column(String(255), nullable=True)

    # Who sent it. Null for admin-issued / CLI-issued tokens.
    inviter_user_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Internal label for the operator (e.g., "beta-round-1").
    note = Column(String(255), nullable=True)

    # Redemption state.
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    redeemed_by_user_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Optional expiry (NULL = no expiry).
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Single-use (1) or multi-use (>1). use_count is bumped on redemption.
    max_uses = Column(Integer, nullable=False, server_default="1")
    use_count = Column(Integer, nullable=False, server_default="0")
