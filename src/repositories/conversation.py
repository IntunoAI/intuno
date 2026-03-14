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
        """
        Create a new conversation.
        :param conversation: Conversation
        :return: Conversation
        """
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_by_id(self, conversation_id: UUID) -> Optional[Conversation]:
        """
        Get conversation by ID.
        :param conversation_id: UUID
        :return: Optional[Conversation]
        """
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(
        self,
        user_id: UUID,
        integration_id: Optional[UUID] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Conversation]:
        """
        Get conversations for a user, optionally filtered by integration_id and external_user_id.
        :param user_id: UUID
        :param integration_id: Optional[UUID]
        :param external_user_id: Optional[str]
        :return: List[Conversation]
        """
        q = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
        )
        if integration_id is not None:
            q = q.where(Conversation.integration_id == integration_id)
        if external_user_id is not None:
            q = q.where(Conversation.external_user_id == external_user_id)
        result = await self.session.execute(q)
        return list(result.scalars().all())

    async def update(self, conversation: Conversation) -> Conversation:
        """
        Update a conversation (fields already set on entity).
        :param conversation: Conversation
        :return: Conversation
        """
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def delete(self, conversation_id: UUID) -> bool:
        """
        Delete conversation by ID.
        :param conversation_id: UUID
        :return: bool
        """
        result = await self.session.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conversation = result.scalar_one_or_none()
        if conversation:
            await self.session.delete(conversation)
            await self.session.commit()
            return True
        return False
