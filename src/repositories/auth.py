"""Auth domain repository."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.auth import ApiKey, User


class AuthRepository:
    """Repository for auth domain operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # User operations
    async def create_user(self, user: User) -> User:
        """Create a new user."""
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def update_user(self, user: User) -> User:
        """Update user."""
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete user by ID."""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            await self.session.delete(user)
            await self.session.commit()
            return True
        return False

    # API Key operations
    async def create_api_key(self, api_key: ApiKey) -> ApiKey:
        """Create a new API key."""
        self.session.add(api_key)
        await self.session.commit()
        await self.session.refresh(api_key)
        return api_key

    async def get_api_key_by_id(self, key_id: UUID) -> Optional[ApiKey]:
        """Get API key by ID."""
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        )
        return result.scalar_one_or_none()

    async def get_api_key_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        """Get API key by hash."""
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        return result.scalar_one_or_none()

    async def get_api_keys_by_user_id(self, user_id: UUID) -> List[ApiKey]:
        """Get all API keys for a user."""
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id)
        )
        return list(result.scalars().all())

    async def update_api_key_last_used(self, key_id: UUID) -> None:
        """Update last used timestamp."""
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            api_key.last_used_at = datetime.utcnow()
            await self.session.commit()

    async def delete_api_key(self, key_id: UUID) -> bool:
        """Delete API key by ID."""
        result = await self.session.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        )
        api_key = result.scalar_one_or_none()
        if api_key:
            await self.session.delete(api_key)
            await self.session.commit()
            return True
        return False
