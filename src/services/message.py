"""Message domain service."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status

from src.models.message import Message
from src.repositories.conversation import ConversationRepository
from src.repositories.message import MessageRepository
from src.schemas.message import MessageCreate


class MessageService:
    """Service for message operations."""

    def __init__(
        self,
        message_repository: MessageRepository = Depends(),
        conversation_repository: ConversationRepository = Depends(),
    ):
        self.message_repository = message_repository
        self.conversation_repository = conversation_repository

    async def create(
        self,
        conversation_id: UUID,
        user_id: UUID,
        data: MessageCreate,
    ) -> Message:
        """Create a message in a conversation. Validates conversation belongs to user."""
        conversation = await self.conversation_repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        message = Message(
            conversation_id=conversation_id,
            role=data.role,
            content=data.content,
            metadata_=data.metadata,
        )
        return await self.message_repository.create(message)

    async def list(
        self,
        conversation_id: UUID,
        user_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Message]:
        """List messages for a conversation (user-scoped)."""
        conversation = await self.conversation_repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            return []
        return await self.message_repository.get_by_conversation_id(
            conversation_id, limit=limit, offset=offset
        )
