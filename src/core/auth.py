"""Authentication dependencies."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, Header

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.core.settings import settings
from src.exceptions import BadRequestException, UnauthorizedException
from src.models.auth import User
from src.services.auth import AuthService
from src.core.security import api_key_header

# Security scheme for token authentication (requires token)
security = HTTPBearer(auto_error=False)
# Security scheme for token-only endpoints (raises error if missing)
security_required = HTTPBearer()


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_required),
    auth_service: AuthService = Depends(),
) -> User:
    """Get current user from JWT token."""
    
    user_id = auth_service.verify_token(credentials.credentials)
    
    if user_id is None:
        raise UnauthorizedException("Invalid authentication credentials")

    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        raise UnauthorizedException("User not found or inactive")

    if not user.is_active:
        raise UnauthorizedException("User not found or inactive")
    
    return user


async def get_current_user_from_api_key(
    x_api_key: str = Depends(lambda: None),  # This will be set by middleware
    auth_service: AuthService = Depends(),
) -> User:
    """Get current user from API key."""
    
    if not x_api_key:
        raise UnauthorizedException("API key required")

    user = await auth_service.verify_api_key(x_api_key)

    if user is None:
        raise UnauthorizedException("Invalid API key or user inactive")

    if not user.is_active:
        raise UnauthorizedException("Invalid API key or user inactive")
    
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Depends(lambda: None),
    auth_service: AuthService = Depends(),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None."""
    
    # Try JWT token first
    if credentials:
        user_id = auth_service.verify_token(credentials.credentials)
        if user_id:
            user = await auth_service.get_user_by_id(user_id)
            if user and user.is_active:
                return user
    # Try API key
    if x_api_key:
        user = await auth_service.verify_api_key(x_api_key)
        if user and user.is_active:
            return user
    return None


# Convenience dependency that tries both methods
async def get_current_user(
    auth_service: AuthService = Depends(),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Depends(api_key_header),
) -> User:
    """Get current user from either JWT token or API key."""

    # Try JWT token first
    if credentials:
        user_id = auth_service.verify_token(credentials.credentials)
        if user_id:
            user = await auth_service.get_user_by_id(user_id)
            if user and user.is_active:
                return user

    # Try API key
    if api_key:
        user = await auth_service.verify_api_key(api_key)
        if user and user.is_active:
            return user

    # Neither method worked
    raise UnauthorizedException("Not authenticated")


async def get_current_user_or_service(
    auth_service: AuthService = Depends(),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Depends(api_key_header),
    x_service_key: Optional[str] = Header(default=None, alias="X-Service-Key"),
    x_on_behalf_of: Optional[str] = Header(default=None, alias="X-On-Behalf-Of"),
) -> User:
    """Accept user JWT / API key *or* service-key delegation.

    Service delegation: the caller presents ``X-Service-Key`` matching
    ``settings.AGENTS_SERVICE_API_KEY`` and ``X-On-Behalf-Of: <user_uuid>``.
    The returned ``User`` is the delegated-to user. Used by wisdom-agents
    so each entity's network / broker / registry calls are attributed to
    the entity's owner instead of a shared account.

    The service key is infra-level (env-only, not DB-backed). Treat leaks
    the same way you'd treat any root credential.
    """
    # Service mode — only if the service-key header is present and matches
    if x_service_key is not None:
        configured = settings.AGENTS_SERVICE_API_KEY
        if not configured or x_service_key != configured:
            raise UnauthorizedException("Invalid service key")
        if not x_on_behalf_of:
            raise BadRequestException(
                "X-On-Behalf-Of header is required when X-Service-Key is set",
            )
        try:
            target_id = UUID(x_on_behalf_of)
        except (ValueError, TypeError) as exc:
            raise BadRequestException(
                "X-On-Behalf-Of must be a valid UUID",
            ) from exc
        user = await auth_service.get_user_by_id(target_id)
        if user is None or not user.is_active:
            raise UnauthorizedException("Delegated user not found or inactive")
        return user

    # Fall through to the normal user-auth flow
    return await get_current_user(
        auth_service=auth_service,
        credentials=credentials,
        api_key=api_key,
    )
