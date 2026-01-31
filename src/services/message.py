"""Message domain service."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends

from src.exceptions import NotFoundException
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
            raise NotFoundException("Conversation")
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

    async def get(
        self,
        conversation_id: UUID,
        message_id: UUID,
        user_id: UUID,
    ) -> Optional[Message]:
        """Get a message by ID (user-scoped via conversation ownership)."""
        conversation = await self.conversation_repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            return None
        message = await self.message_repository.get_by_id(message_id)
        if not message or message.conversation_id != conversation_id:
            return None
        return message

    async def delete(
        self,
        conversation_id: UUID,
        message_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Delete a message (user-scoped via conversation ownership)."""
        message = await self.get(conversation_id, message_id, user_id)
        if not message:
            return False
        return await self.message_repository.delete(message_id)
