"""Authentication routes."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import get_current_user
from src.database import get_db
from src.models.auth import User
from src.schemas.auth import (
    ApiKeyCreate,
    ApiKeyListResponse,
    ApiKeyResponse,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from src.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user.
    :param user_data: UserRegister
    :param db: AsyncSession
    :return: UserResponse
    """
    auth_service = AuthService(db)
    
    try:
        user = await auth_service.register_user(user_data)
        return UserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Login and get access token.
    :param login_data: UserLogin
    :param db: AsyncSession
    :return: TokenResponse
    """
    auth_service = AuthService(db)
    
    user = await auth_service.authenticate_user(login_data)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    
    access_token = auth_service.create_access_token(user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=60 * 60 * 24 * 7,  # 7 days in seconds
    )


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    api_key_data: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key.
    :param api_key_data: ApiKeyCreate
    :param current_user: User
    :param db: AsyncSession
    :return: ApiKeyResponse
    """
    auth_service = AuthService(db)
    
    api_key_record, api_key = await auth_service.create_api_key(current_user.id, api_key_data)
    
    return ApiKeyResponse(
        id=api_key_record.id,
        name=api_key_record.name,
        key=api_key,  # Only returned on creation
        created_at=api_key_record.created_at,
        last_used_at=api_key_record.last_used_at,
        expires_at=api_key_record.expires_at,
    )


@router.get("/api-keys", response_model=List[ApiKeyListResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's API keys.
    :param current_user: User
    :param db: AsyncSession
    :return: List[ApiKeyListResponse]
    """
    auth_service = AuthService(db)
    
    api_keys = await auth_service.get_user_api_keys(current_user.id)
    
    return [
        ApiKeyListResponse(
            id=key.id,
            name=key.name,
            created_at=key.created_at,
            last_used_at=key.last_used_at,
            expires_at=key.expires_at,
        )
        for key in api_keys
    ]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an API key.
    :param key_id: UUID
    :param current_user: User
    :param db: AsyncSession
    :return: None
    """
    auth_service = AuthService(db)
    
    success = await auth_service.delete_api_key(current_user.id, key_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current user information.
    :param current_user: User
    :return: UserResponse
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )
