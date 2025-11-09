from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from starlette import status

from src.models.auth import User
from src.services.auth import AuthService

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing",
        )

    user = await auth_service.verify_api_key(api_key)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    return user
