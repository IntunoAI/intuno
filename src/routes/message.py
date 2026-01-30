"""Message routes: get, update, delete by message_id (under a conversation)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth import get_current_user
from src.models.auth import User
from src.schemas.message import MessageResponse, MessageUpdate
from src.services.message import MessageService

router = APIRouter(
    prefix="/conversations/{conversation_id}/messages",
    tags=["Messages"],
)


@router.get("/{message_id}", response_model=MessageResponse)
async def get_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> MessageResponse:
    """Get a message by ID (user-scoped via conversation ownership)."""
    message = await message_service.get(
        conversation_id, message_id, current_user.id
    )
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        metadata=message.metadata_,
        created_at=message.created_at,
    )


@router.patch("/{message_id}", response_model=MessageResponse)
async def update_message(
    conversation_id: UUID,
    message_id: UUID,
    data: MessageUpdate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> MessageResponse:
    """Update a message (user-scoped via conversation ownership)."""
    message = await message_service.update(
        conversation_id, message_id, current_user.id, data
    )
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        metadata=message.metadata_,
        created_at=message.created_at,
    )


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> None:
    """Delete a message (user-scoped via conversation ownership)."""
    success = await message_service.delete(
        conversation_id, message_id, current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
