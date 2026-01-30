"""Conversation domain repository."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.conversation import Conversation


class ConversationRepository:
    """Repository for conversation domain operations."""

    def __init__(self, session: AsyncSession = Depends(get_db)):
        self.session = session

    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_by_id(self, conversation_id: UUID) -> Optional[Conversation]:
        """Get conversation by ID."""
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
        integration_id: Optional[UUID] = None,
    ) -> List[Conversation]:
        """Get conversations for a user, optionally filtered by integration_id."""
        q = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
        )
        if integration_id is not None:
            q = q.where(Conversation.integration_id == integration_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())
