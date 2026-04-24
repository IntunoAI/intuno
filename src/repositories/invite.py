"""Repository for user_invites — CRUD only, business rules live in the service."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.user_invite import UserInvite


class InviteRepository:
    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def get_by_token(self, token: str) -> Optional[UserInvite]:
        result = await self.session.execute(
            select(UserInvite).where(UserInvite.token == token)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, invite_id: UUID) -> Optional[UserInvite]:
        result = await self.session.execute(
            select(UserInvite).where(UserInvite.id == invite_id)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        unredeemed_only: bool = False,
        include_expired: bool = True,
        limit: int = 100,
    ) -> List[UserInvite]:
        stmt = select(UserInvite).order_by(UserInvite.created_at.desc()).limit(limit)
        if unredeemed_only:
            stmt = stmt.where(UserInvite.redeemed_at.is_(None))
        if not include_expired:
            now = datetime.now(tz=timezone.utc)
            stmt = stmt.where(
                (UserInvite.expires_at.is_(None)) | (UserInvite.expires_at > now)
            )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, invite: UserInvite) -> UserInvite:
        self.session.add(invite)
        await self.session.commit()
        await self.session.refresh(invite)
        return invite

    async def mark_redeemed(
        self, invite_id: UUID, redeemed_by_user_id: UUID
    ) -> Optional[UserInvite]:
        """Atomic: set redeemed_at + increment use_count. Returns the row, or
        None if the invite disappeared between lookup and commit."""
        now = datetime.now(tz=timezone.utc)
        result = await self.session.execute(
            update(UserInvite)
            .where(UserInvite.id == invite_id)
            .values(
                redeemed_at=now,
                redeemed_by_user_id=redeemed_by_user_id,
                use_count=UserInvite.use_count + 1,
            )
            .returning(UserInvite)
        )
        row = result.scalar_one_or_none()
        await self.session.commit()
        return row

    async def delete(self, invite_id: UUID) -> bool:
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(UserInvite).where(UserInvite.id == invite_id)
        )
        await self.session.commit()
        return (result.rowcount or 0) > 0
