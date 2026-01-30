"""Message routes: get, update, delete by message_id (under a conversation)."""

from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.core.auth import get_current_user
from src.exceptions import NotFoundException
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
    """Get a message by ID (user-scoped via conversation ownership).
    :param conversation_id: UUID
    :param message_id: UUID
    :param current_user: User
    :param message_service: MessageService
    :return: MessageResponse
    """
    message = await message_service.get(
        conversation_id, message_id, current_user.id
    )
    if not message:
        raise NotFoundException("Message")
    return message


@router.patch("/{message_id}", response_model=MessageResponse)
async def update_message(
    conversation_id: UUID,
    message_id: UUID,
    data: MessageUpdate,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> MessageResponse:
    """Update a message (user-scoped via conversation ownership).
    :param conversation_id: UUID
    :param message_id: UUID
    :param data: MessageUpdate
    :param current_user: User
    :param message_service: MessageService
    :return: MessageResponse
    """
    message = await message_service.update(
        conversation_id, message_id, current_user.id, data
    )
    if not message:
        raise NotFoundException("Message")
    return message


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: User = Depends(get_current_user),
    message_service: MessageService = Depends(),
) -> None:
    """Delete a message (user-scoped via conversation ownership).
    :param conversation_id: UUID
    :param message_id: UUID
    :param current_user: User
    :param message_service: MessageService
    :return: None
    """
    success = await message_service.delete(
        conversation_id, message_id, current_user.id
    )
    if not success:
        raise NotFoundException("Message")
