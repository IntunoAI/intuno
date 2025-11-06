"""Authentication dependencies."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.models.auth import User
from src.services.auth import AuthService

# Security scheme
security = HTTPBearer()


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(),
) -> User:
    """Get current user from JWT token."""
    user_id = auth_service.verify_token(credentials.credentials)
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await auth_service.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return user


async def get_current_user_from_api_key(
    x_api_key: str = Depends(lambda: None),  # This will be set by middleware
    auth_service: AuthService = Depends(),
) -> User:
    """Get current user from API key."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )
    
    user = await auth_service.verify_api_key(x_api_key)
    
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key or user inactive",
        )
    
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
) -> User:
    """Get current user from either JWT token or API key."""
    
    # Try JWT token first
    if credentials:
        user_id = auth_service.verify_token(credentials.credentials)
        if user_id:
            user = await auth_service.get_user_by_id(user_id)
            if user and user.is_active:
                return user
    
    # Try API key from header (this would need custom middleware)
    # For now, just raise if no JWT token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
