"""Conversation domain service."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends

from src.exceptions import BadRequestException
from src.models.conversation import Conversation
from src.repositories.conversation import ConversationRepository
from src.repositories.integration import IntegrationRepository
from src.services.invocation_log import InvocationLogService
from src.schemas.conversation import ConversationCreate, ConversationUpdate


class ConversationService:
    """Service for conversation operations."""

    def __init__(
        self,
        conversation_repository: ConversationRepository = Depends(),
        invocation_log_service: InvocationLogService = Depends(),
        integration_repository: IntegrationRepository = Depends(),
    ):
        self.conversation_repository = conversation_repository
        self.invocation_log_service = invocation_log_service
        self.integration_repository = integration_repository

    async def create(self, user_id: UUID, data: ConversationCreate) -> Conversation:
        """Create a new conversation. Validates integration_id belongs to user if provided."""
        integration_id = data.integration_id
        if integration_id is not None:
            integration = await self.integration_repository.get_by_id(integration_id)
            if not integration or integration.user_id != user_id:
                raise BadRequestException("Integration not found or not owned by user")
        conversation = Conversation(
            user_id=user_id,
            integration_id=integration_id,
            title=data.title,
        )
        return await self.conversation_repository.create(conversation)

    async def list(
        self,
        user_id: UUID,
        integration_id: Optional[UUID] = None,
        external_user_id: Optional[str] = None,
    ) -> List[Conversation]:
        """List conversations for the user, optionally filtered by integration_id and external_user_id."""
        return await self.conversation_repository.get_by_user_id(
            user_id, integration_id, external_user_id
        )

    async def get(self, conversation_id: UUID, user_id: UUID) -> Optional[Conversation]:
        """Get conversation by ID if owned by user."""
        conversation = await self.conversation_repository.get_by_id(conversation_id)
        if not conversation or conversation.user_id != user_id:
            return None
        return conversation

    async def update(
        self,
        conversation_id: UUID,
        user_id: UUID,
        data: ConversationUpdate,
    ) -> Optional[Conversation]:
        """Update a conversation (user-scoped). Validates integration_id belongs to user if provided."""
        conversation = await self.get(conversation_id, user_id)
        if not conversation:
            return None
        if data.title is not None:
            conversation.title = data.title
        if data.integration_id is not None:
            integration = await self.integration_repository.get_by_id(data.integration_id)
            if not integration or integration.user_id != user_id:
                raise BadRequestException("Integration not found or not owned by user")
            conversation.integration_id = data.integration_id
        return await self.conversation_repository.update(conversation)

    async def delete(self, conversation_id: UUID, user_id: UUID) -> bool:
        """Delete a conversation (user-scoped)."""
        conversation = await self.get(conversation_id, user_id)
        if not conversation:
            return False
        return await self.conversation_repository.delete(conversation_id)

    async def get_logs(
        self,
        conversation_id: UUID,
        user_id: UUID,
        limit: int = 50,
    ) -> List:
        """Get invocation logs for a conversation (user-scoped)."""
        conversation = await self.get(conversation_id, user_id)
        if not conversation:
            return []
        return await self.invocation_log_service.get_logs_for_conversation(
            conversation_id=conversation_id,
            user_id=user_id,
            limit=limit,
        )
