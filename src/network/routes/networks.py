"""Network routes: CRUD for communication networks, participants, and context."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.auth import get_current_user_or_service as get_current_user
from src.exceptions import NotFoundException
from src.models.auth import User
from src.network.models.schemas import (
    NetworkContextSnapshot,
    NetworkCreate,
    NetworkMessageResponse,
    NetworkResponse,
    NetworkUpdate,
    ParticipantJoin,
    ParticipantResponse,
    ParticipantUpdate,
)
from src.network.services.networks import NetworkService

router = APIRouter(prefix="/networks", tags=["Networks"])


# ── Networks ─────────────────────────────────────────────────────────


@router.post("", response_model=NetworkResponse, status_code=status.HTTP_201_CREATED)
async def create_network(
    data: NetworkCreate,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> NetworkResponse:
    network = await service.create_network(current_user.id, data)
    return network


@router.get("", response_model=List[NetworkResponse])
async def list_networks(
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: NetworkService = Depends(),
) -> List[NetworkResponse]:
    return await service.list_networks(current_user.id, limit, offset)


@router.get("/{network_id}", response_model=NetworkResponse)
async def get_network(
    network_id: UUID,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> NetworkResponse:
    return await service.get_network(network_id, current_user.id)


@router.patch("/{network_id}", response_model=NetworkResponse)
async def update_network(
    network_id: UUID,
    data: NetworkUpdate,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> NetworkResponse:
    return await service.update_network(network_id, current_user.id, data)


@router.delete("/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_network(
    network_id: UUID,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> None:
    success = await service.delete_network(network_id, current_user.id)
    if not success:
        raise NotFoundException("Network")


# ── Participants ─────────────────────────────────────────────────────


@router.post(
    "/{network_id}/participants",
    response_model=ParticipantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def join_network(
    network_id: UUID,
    data: ParticipantJoin,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> ParticipantResponse:
    return await service.join_network(network_id, current_user.id, data)


@router.get(
    "/{network_id}/participants",
    response_model=List[ParticipantResponse],
)
async def list_participants(
    network_id: UUID,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> List[ParticipantResponse]:
    return await service.list_participants(network_id, current_user.id)


@router.patch(
    "/{network_id}/participants/{participant_id}",
    response_model=ParticipantResponse,
)
async def update_participant(
    network_id: UUID,
    participant_id: UUID,
    data: ParticipantUpdate,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> ParticipantResponse:
    return await service.update_participant(
        network_id, participant_id, current_user.id, data
    )


@router.delete(
    "/{network_id}/participants/{participant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def leave_network(
    network_id: UUID,
    participant_id: UUID,
    current_user: User = Depends(get_current_user),
    service: NetworkService = Depends(),
) -> None:
    success = await service.leave_network(network_id, participant_id, current_user.id)
    if not success:
        raise NotFoundException("Participant")


# ── Context ──────────────────────────────────────────────────────────


@router.get("/{network_id}/context")
async def get_network_context(
    network_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    service: NetworkService = Depends(),
) -> dict:
    entries = await service.get_context(network_id, current_user.id, limit)
    return {
        "network_id": str(network_id),
        "entries": entries,
    }


# ── Messages ─────────────────────────────────────────────────────────


@router.get(
    "/{network_id}/messages",
    response_model=List[NetworkMessageResponse],
)
async def list_messages(
    network_id: UUID,
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    channel_type: str | None = Query(default=None),
    participant_id: UUID | None = Query(default=None),
    service: NetworkService = Depends(),
) -> List[NetworkMessageResponse]:
    return await service.list_messages(
        network_id, current_user.id, limit, offset, channel_type, participant_id
    )
