"""Conversation routes: CRUD, logs, and message list/create."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import get_current_user
from src.exceptions import NotFoundException
from src.models.auth import User
from src.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)
from src.schemas.invocation_log import InvocationLogResponse
from src.schemas.message import MessageCreate, MessageListResponse, MessageResponse
from src.services.conversation import ConversationService
from src.services.message import MessageService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """Create a new conversation (optional title and integration_id)."""
    conversation = await conversation_service.create(current_user.id, data)
    return conversation


@router.get("", response_model=List[ConversationListResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    integration_id: UUID | None = Query(default=None),
    conversation_service: ConversationService = Depends(),
) -> List[ConversationListResponse]:
    """List conversations for the current user (optional filter by integration_id)."""
    conversations = await conversation_service.list(current_user.id, integration_id)
    return conversations


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """Get a conversation by ID (user-scoped)."""
    conversation = await conversation_service.get(conversation_id, current_user.id)
    if not conversation:
        raise NotFoundException("Conversation")
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    data: ConversationUpdate,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """Update a conversation (user-scoped)."""
    conversation = await conversation_service.update(
        conversation_id, current_user.id, data
    )
    if not conversation:
        raise NotFoundException("Conversation")
    return conversation


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> None:
    """Delete a conversation (user-scoped)."""
    success = await conversation_service.delete(conversation_id, current_user.id)
    if not success:
        raise NotFoundException("Conversation")


@router.get("/{conversation_id}/logs", response_model=List[InvocationLogResponse])
async def get_conversation_logs(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    conversation_service: ConversationService = Depends(),
) -> List[InvocationLogResponse]:
    """Get invocation logs for this conversation (user-scoped)."""
    return await conversation_service.get_logs(
        conversation_id, current_user.id, limit=limit
    )


@router.get("/{conversation_id}/messages", response_model=List[MessageListResponse])
async def list_conversation_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    message_service: MessageService = Depends(),
) -> List[MessageListResponse]:
    """List messages for this conversation (user-scoped, ordered by created_at)."""
    messages = await message_service.list(
        conversation_id, current_user.id, limit=limit, offset=offset
    )
    return messages


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: UUID,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> MessageResponse:
    """Add a message to this conversation (user-scoped)."""
    message = await message_service.create(
        conversation_id, current_user.id, data
    )
    return message
