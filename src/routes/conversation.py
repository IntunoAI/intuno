"""Conversation routes: read-only (list, get, update, delete, logs, message list). Creation is internal (broker/orchestrator)."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import get_current_user
from src.exceptions import NotFoundException
from src.models.auth import User
from src.schemas.conversation import (
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)
from src.schemas.invocation_log import InvocationLogResponse
from src.schemas.message import MessageListResponse
from src.services.conversation import ConversationService
from src.services.message import MessageService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get(
    "",
    response_model=List[ConversationListResponse],
)
async def list_conversations(
    current_user: User = Depends(get_current_user),
    integration_id: UUID | None = Query(default=None),
    external_user_id: str | None = Query(default=None),
    conversation_service: ConversationService = Depends(),
) -> List[ConversationListResponse]:
    """
    List conversations for the current user (optional filter by integration_id, external_user_id).
    :param current_user: User
    :param integration_id: Optional[UUID]
    :param external_user_id: Optional client end-user id for audit filter
    :param conversation_service: ConversationService
    :return: List[ConversationListResponse]
    """
    conversations = await conversation_service.list(
        current_user.id, integration_id, external_user_id
    )
    return conversations


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """
    Get a conversation by ID (user-scoped).
    :param conversation_id: UUID
    :param current_user: User
    :param conversation_service: ConversationService
    :return: ConversationResponse
    """
    conversation = await conversation_service.get(conversation_id, current_user.id)
    if not conversation:
        raise NotFoundException("Conversation")
    return conversation


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
)
async def update_conversation(
    conversation_id: UUID,
    data: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """Update a conversation (user-scoped).
    :param conversation_id: UUID
    :param data: ConversationUpdate
    :param current_user: User
    :param conversation_service: ConversationService
    :return: ConversationResponse
    """
    conversation = await conversation_service.update(
        conversation_id, current_user.id, data
    )
    if not conversation:
        raise NotFoundException("Conversation")
    return conversation


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> None:
    """Delete a conversation (user-scoped).
    :param conversation_id: UUID
    :param current_user: User
    :param conversation_service: ConversationService
    :return: None
    """
    success = await conversation_service.delete(conversation_id, current_user.id)
    if not success:
        raise NotFoundException("Conversation")


@router.get(
    "/{conversation_id}/logs",
    response_model=List[InvocationLogResponse],
)
async def get_conversation_logs(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    conversation_service: ConversationService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for this conversation (user-scoped).
    :param conversation_id: UUID
    :param current_user: User
    :param limit: int
    :param conversation_service: ConversationService
    :return: List[InvocationLogResponse]
    """
    return await conversation_service.get_logs(
        conversation_id, current_user.id, limit=limit
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=List[MessageListResponse],
)
async def list_conversation_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    message_service: MessageService = Depends(),
) -> List[MessageListResponse]:
    """List messages for this conversation (user-scoped, ordered by created_at).
    :param conversation_id: UUID
    :param current_user: User
    :param limit: int
    :param offset: int
    :param message_service: MessageService
    :return: List[MessageListResponse]
    """
    messages = await message_service.list(
        conversation_id, current_user.id, limit=limit, offset=offset
    )
    return messages
