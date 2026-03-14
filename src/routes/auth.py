"""Authentication routes."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, status

from src.core.auth import get_current_user
from src.exceptions import BadRequestException, NotFoundException, UnauthorizedException
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


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    user_data: UserRegister,
    auth_service: AuthService = Depends(),
) -> UserResponse:
    """
    Register a new user.
    :param user_data: UserRegister
    :param auth_service: AuthService
    :return: UserResponse
    """
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
        raise BadRequestException(str(e))


@router.post(
    "/login",
    response_model=TokenResponse,
)
async def login(
    login_data: UserLogin,
    auth_service: AuthService = Depends(),
) -> TokenResponse:
    """
    Login and get access token.
    :param login_data: UserLogin
    :param auth_service: AuthService
    :return: TokenResponse
    """
    user = await auth_service.authenticate_user(login_data)
    if not user:
        raise UnauthorizedException("Invalid email or password")
    
    access_token = auth_service.create_access_token(user.id)
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=60 * 60 * 24 * 7,  # 7 days in seconds
    )


@router.post(
    "/api-keys",
    response_model=ApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    api_key_data: ApiKeyCreate,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(),
) -> ApiKeyResponse:
    """
    Create a new API key.
    :param api_key_data: ApiKeyCreate
    :param current_user: User
    :param auth_service: AuthService
    :return: ApiKeyResponse
    """
    api_key_record, api_key = await auth_service.create_api_key(current_user.id, api_key_data)
    
    return ApiKeyResponse(
        id=api_key_record.id,
        name=api_key_record.name,
        key=api_key,  # Only returned on creation
        created_at=api_key_record.created_at,
        last_used_at=api_key_record.last_used_at,
        expires_at=api_key_record.expires_at,
    )


@router.get(
    "/api-keys",
    response_model=List[ApiKeyListResponse],
)
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(),
) -> List[ApiKeyListResponse]:
    """
    List user's API keys.
    :param current_user: User
    :param auth_service: AuthService
    :return: List[ApiKeyListResponse]
    """
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


@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """
    Get current user information.
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


@router.delete(
    "/api-keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_api_key(
    key_id: UUID,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(),
) -> None:
    """
    Delete an API key.
    :param key_id: UUID
    :param current_user: User
    :param auth_service: AuthService
    :return: None
    """
    
    success = await auth_service.delete_api_key(current_user.id, key_id)
    if not success:
        raise NotFoundException("API key")
