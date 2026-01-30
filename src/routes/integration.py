"""Integration routes."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.core.auth import get_current_user
from src.exceptions import NotFoundException
from src.models.auth import User
from src.schemas.auth import ApiKeyCreate, ApiKeyListResponse, ApiKeyResponse
from src.schemas.integration import (
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
)
from src.services.integration import IntegrationService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.post(
    "",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    data: IntegrationCreate,
    current_user: User = Depends(get_current_user),
    integration_service: IntegrationService = Depends(),
) -> IntegrationResponse:
    """Create a new integration.
    :param data: IntegrationCreate
    :param current_user: User
    :param integration_service: IntegrationService
    :return: IntegrationResponse
    """
    integration = await integration_service.create(current_user.id, data)
    return integration


@router.get("", response_model=List[IntegrationListResponse])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    integration_service: IntegrationService = Depends(),
) -> List[IntegrationListResponse]:
    """List integrations for the current user."""
    integrations = await integration_service.list(current_user.id)
    return integrations


@router.get(
    "/{integration_id}",
    response_model=IntegrationResponse,
)
async def get_integration(
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    integration_service: IntegrationService = Depends(),
) -> IntegrationResponse:
    """Get integration by ID (user-scoped).
    :param integration_id: UUID
    :param current_user: User
    :param integration_service: IntegrationService
    :return: IntegrationResponse
    """
    integration = await integration_service.get(integration_id, current_user.id)
    if not integration:
        raise NotFoundException("Integration")
    return integration


@router.delete(
    "/{integration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_integration(
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    integration_service: IntegrationService = Depends(),
) -> None:
    """Delete integration (user-scoped).
    :param integration_id: UUID
    :param current_user: User
    :param integration_service: IntegrationService
    :return: None
    """
    success = await integration_service.delete(integration_id, current_user.id)
    if not success:
        raise NotFoundException("Integration")


@router.get(
    "/{integration_id}/api-keys",
    response_model=List[ApiKeyListResponse],
)
async def list_integration_api_keys(
    integration_id: UUID,
    current_user: User = Depends(get_current_user),
    integration_service: IntegrationService = Depends(),
) -> List[ApiKeyListResponse]:
    """List API keys for an integration (no raw key).
    :param integration_id: UUID
    :param current_user: User
    :param integration_service: IntegrationService
    :return: List[ApiKeyListResponse]
    """
    integration = await integration_service.get(integration_id, current_user.id)
    if not integration:
        raise NotFoundException("Integration")
    return [
        ApiKeyListResponse(
            id=key.id,
            name=key.name,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
        )
        for key in integration.api_keys
    ]


@router.post(
    "/{integration_id}/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration_api_key(
    integration_id: UUID, api_key_data: ApiKeyCreate, current_user: User = Depends(get_current_user), integration_service: IntegrationService = Depends(),
) -> ApiKeyResponse:
    """Create an API key for an integration. Raw key returned only on creation.
    :param integration_id: UUID
    :param api_key_data: ApiKeyCreate
    :param current_user: User
    :param integration_service: IntegrationService
    :return: ApiKeyResponse
    """
    api_key_record, raw_key = await integration_service.create_api_key_for_integration(current_user.id, integration_id, api_key_data)
    return ApiKeyResponse(
        id=api_key_record.id,
        name=api_key_record.name,
        key=raw_key,
        created_at=api_key_record.created_at,
        last_used_at=api_key_record.last_used_at,
        expires_at=api_key_record.expires_at,
    )


@router.delete(
    "/{integration_id}/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_integration_api_key(
    integration_id: UUID,
    key_id: UUID,
    current_user: User = Depends(get_current_user),
    integration_service: IntegrationService = Depends(),
) -> None:
    """Revoke an API key that belongs to this integration (user-scoped).
    :param integration_id: UUID
    :param key_id: UUID
    :param current_user: User
    :param integration_service: IntegrationService
    :return: None
    """
    success = await integration_service.revoke_api_key_for_integration(
        current_user.id, integration_id, key_id
    )
    if not success:
        raise NotFoundException("Integration or API key")
