"""Authentication dependencies."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.auth import User
from src.services.auth import AuthService

# Security scheme
security = HTTPBearer()


async def get_current_user_from_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from JWT token."""
    auth_service = AuthService(db)
    user_id = auth_service.verify_token(credentials.credentials)
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = await auth_service.repository.get_user_by_id(user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return user


async def get_current_user_from_api_key(
    x_api_key: str = Depends(lambda: None),  # This will be set by middleware
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current user from API key."""
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
        )
    
    auth_service = AuthService(db)
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
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user if authenticated, otherwise return None."""
    auth_service = AuthService(db)
    
    # Try JWT token first
    if credentials:
        user_id = auth_service.verify_token(credentials.credentials)
        if user_id:
            user = await auth_service.repository.get_user_by_id(user_id)
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
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """Get current user from either JWT token or API key."""
    auth_service = AuthService(db)
    
    # Try JWT token first
    if credentials:
        user_id = auth_service.verify_token(credentials.credentials)
        if user_id:
            user = await auth_service.repository.get_user_by_id(user_id)
            if user and user.is_active:
                return user
    
    # Try API key from header (this would need custom middleware)
    # For now, just raise if no JWT token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
