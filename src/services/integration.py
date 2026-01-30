"""Integration domain service."""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends

from src.exceptions import NotFoundException
from src.models.integration import Integration
from src.repositories.integration import IntegrationRepository
from src.schemas.integration import IntegrationCreate, IntegrationListResponse, IntegrationResponse
from src.schemas.auth import ApiKeyCreate, ApiKeyResponse
from src.services.auth import AuthService


class IntegrationService:
    """Service for integration operations."""

    def __init__(
        self,
        integration_repository: IntegrationRepository = Depends(),
        auth_service: AuthService = Depends(),
    ):
        self.integration_repository = integration_repository
        self.auth_service = auth_service

    async def create(self, user_id: UUID, data: IntegrationCreate) -> Integration:
        """Create a new integration for the user."""
        integration = Integration(
            user_id=user_id,
            name=data.name,
            kind=data.kind,
            metadata_=data.metadata,
        )
        return await self.integration_repository.create(integration)

    async def list(self, user_id: UUID) -> List[Integration]:
        """List integrations for the user."""
        return await self.integration_repository.get_by_user_id(user_id)

    async def get(self, integration_id: UUID, user_id: UUID) -> Optional[Integration]:
        """Get integration by ID if owned by user."""
        integration = await self.integration_repository.get_by_id(integration_id)
        if not integration or integration.user_id != user_id:
            return None
        return integration

    async def delete(self, integration_id: UUID, user_id: UUID) -> bool:
        """Delete integration if owned by user."""
        integration = await self.integration_repository.get_by_id(integration_id)
        if not integration or integration.user_id != user_id:
            return False
        return await self.integration_repository.delete(integration_id)

    async def create_api_key_for_integration(
        self,
        user_id: UUID,
        integration_id: UUID,
        api_key_data: ApiKeyCreate,
    ) -> tuple:
        """Create an API key tied to the integration. Returns (ApiKey record, raw key string)."""
        integration = await self.get(integration_id, user_id)
        if not integration:
            raise NotFoundException("Integration")
        return await self.auth_service.create_api_key(
            user_id=user_id,
            api_key_data=api_key_data,
            integration_id=integration_id,
        )

    async def revoke_api_key_for_integration(
        self,
        user_id: UUID,
        integration_id: UUID,
        key_id: UUID,
    ) -> bool:
        """Revoke an API key that belongs to this integration. Returns True if deleted."""
        integration = await self.get(integration_id, user_id)
        if not integration:
            return False
        return await self.auth_service.delete_api_key_for_integration(
            user_id=user_id,
            integration_id=integration_id,
            key_id=key_id,
        )
