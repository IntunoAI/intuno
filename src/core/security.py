from typing import Optional, Tuple
from uuid import UUID

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from starlette import status

from src.exceptions import UnauthorizedException
from src.models.auth import User
from src.services.auth import AuthService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


async def get_user_from_api_key(
    api_key: str = Security(api_key_header),
    auth_service: AuthService = Depends(),
) -> User:
    """
    FastAPI dependency to authenticate a user via an API key.

    Args:
        api_key: The API key from the 'X-API-Key' header.
        auth_service: The authentication service.

    Returns:
        The authenticated User object.

    Raises:
        HTTPException: If the API key is missing, invalid, or expired.
    """
    if not api_key:
        raise UnauthorizedException("API key is missing")

    user = await auth_service.verify_api_key(api_key)
    if not user:
        raise UnauthorizedException("Invalid or expired API key")

    return user


async def get_user_and_integration_from_api_key(
    api_key: str = Security(api_key_header),
    auth_service: AuthService = Depends(),
) -> Tuple[User, Optional[UUID]]:
    """
    Authenticate via API key and return (user, integration_id).
    integration_id is None for personal keys or when not tied to an integration.

    Returns:
        Tuple[User, Optional[UUID]] (user, integration_id).

    Raises:
        HTTPException: If the API key is missing, invalid, or expired.
    """
    if not api_key:
        raise UnauthorizedException("API key is missing")
    ctx = await auth_service.verify_api_key_and_get_context(api_key)
    if not ctx:
        raise UnauthorizedException("Invalid or expired API key")
    user, integration_id = ctx
    return (user, integration_id)


async def get_user_and_integration(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
    auth_service: AuthService = Depends(),
) -> Tuple[User, Optional[UUID]]:
    """
    Authenticate via JWT (Bearer) or X-API-Key. Returns (user, integration_id).
    integration_id is None when using JWT or for personal API keys.
    """
    if credentials:
        user_id = auth_service.verify_token(credentials.credentials)
        if user_id:
            user = await auth_service.get_user_by_id(user_id)
            if user and user.is_active:
                return (user, None)
    if api_key:
        ctx = await auth_service.verify_api_key_and_get_context(api_key)
        if ctx:
            user, integration_id = ctx
            return (user, integration_id)
    raise UnauthorizedException("Not authenticated")
