"""Broker routes: invoke + conversations + messages; log endpoints in invocation_log router."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.auth import get_current_user
from src.core.security import get_user_and_integration_from_api_key
from src.models.auth import User
from src.schemas.broker import InvokeRequest, InvokeResponse
from src.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
)
from src.schemas.message import MessageCreate, MessageListResponse, MessageResponse
from src.services.broker import BrokerService
from src.services.conversation import ConversationService
from src.services.message import MessageService

router = APIRouter(prefix="/broker", tags=["Broker"])


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(
    invoke_request: InvokeRequest,
    user_and_integration: tuple[User, object] = Depends(get_user_and_integration_from_api_key),
    broker_service: BrokerService = Depends(),
):
    """
    Invoke an agent capability through the broker.
    Optional conversation_id and message_id attach the invocation to a conversation/message.
    """
    current_user, integration_id = user_and_integration
    try:
        response = await broker_service.invoke_agent(
            invoke_request,
            caller_user_id=current_user.id,
            integration_id=integration_id,
            conversation_id=invoke_request.conversation_id,
            message_id=invoke_request.message_id,
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Broker error: {str(e)}",
        )


# --- Conversations ---


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """Create a new conversation (optional title and integration_id)."""
    conversation = await conversation_service.create(current_user.id, data)
    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        integration_id=conversation.integration_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("/conversations", response_model=List[ConversationListResponse])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    integration_id: UUID | None = Query(default=None),
    conversation_service: ConversationService = Depends(),
) -> List[ConversationListResponse]:
    """List conversations for the current user (optional filter by integration_id)."""
    conversations = await conversation_service.list(current_user.id, integration_id)
    return [
        ConversationListResponse(
            id=c.id,
            user_id=c.user_id,
            integration_id=c.integration_id,
            title=c.title,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    conversation_service: ConversationService = Depends(),
) -> ConversationResponse:
    """Get a conversation by ID (user-scoped)."""
    conversation = await conversation_service.get(conversation_id, current_user.id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return ConversationResponse(
        id=conversation.id,
        user_id=conversation.user_id,
        integration_id=conversation.integration_id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


# --- Messages ---


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_message(
    conversation_id: UUID,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> MessageResponse:
    """Add a message to a conversation (user-scoped)."""
    message = await message_service.create(conversation_id, current_user.id, data)
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        metadata=message.metadata_,
        created_at=message.created_at,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[MessageListResponse],
)
async def list_conversation_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    message_service: MessageService = Depends(),
) -> List[MessageListResponse]:
    """List messages for a conversation (user-scoped, ordered by created_at)."""
    messages = await message_service.list(conversation_id, current_user.id, limit=limit, offset=offset)
    return [
        MessageListResponse(
            id=m.id,
            conversation_id=m.conversation_id,
            role=m.role,
            content=m.content,
            metadata=m.metadata_,
            created_at=m.created_at,
        )
        for m in messages
    ]
