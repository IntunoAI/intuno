"""Auth domain service."""

import secrets
import bcrypt
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from fastapi import Depends

from src.core.settings import settings
from src.models.auth import ApiKey, User
from src.repositories.auth import AuthRepository
from src.schemas.auth import ApiKeyCreate, UserLogin, UserRegister


class AuthService:
    """Service for authentication operations."""

    def __init__(self, auth_repository: AuthRepository = Depends()):
        self.auth_repository = auth_repository

    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt.
        :param password: str
        :return: str
        """
        # Truncate password to 72 bytes for bcrypt compatibility
        password_bytes = password[:72].encode('utf-8')
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash using bcrypt.
        :param plain_password: str
        :param hashed_password: str
        :return: bool
        """
        try:
            password_bytes = plain_password[:72].encode('utf-8')
            hashed_bytes = hashed_password.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hashed_bytes)
        except (ValueError, TypeError):
            return False

    def create_access_token(self, user_id: UUID) -> str:
        """
        Create a JWT access token.
        :param user_id: UUID
        :return: str
        """
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access"
        }
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[UUID]:
        """
        Verify a JWT token and return user ID.
        :param token: str
        :return: Optional[UUID]
        """
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            return UUID(user_id)
        except (JWTError, ValueError):
            return None

    async def register_user(self, user_data: UserRegister) -> User:
        """
        Register a new user.
        :param user_data: UserRegister
        :return: User
        """
        # Check if user already exists
        existing_user = await self.auth_repository.get_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Truncate password to 72 bytes for bcrypt compatibility
        password = user_data.password[:72]

        # Create new user
        user = User(
            email=user_data.email,
            password_hash=self.hash_password(password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
        )
        return await self.auth_repository.create_user(user)

    async def authenticate_user(self, login_data: UserLogin) -> Optional[User]:
        """
        Authenticate a user with email and password.
        :param login_data: UserLogin
        :return: Optional[User]
        """
        user = await self.auth_repository.get_user_by_email(login_data.email)
        if not user or not self.verify_password(login_data.password, user.password_hash):
            return None
        return user

    def _hash_api_key(self, api_key: str) -> str:
        """
        Hash an API key using SHA256 (deterministic hash for lookup).
        :param api_key: str
        :return: str
        """
        return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

    async def create_api_key(
        self,
        user_id: UUID,
        api_key_data: ApiKeyCreate,
        integration_id: Optional[UUID] = None,
    ) -> tuple[ApiKey, str]:
        """
        Create a new API key for a user, optionally tied to an integration.
        :param user_id: UUID
        :param api_key_data: ApiKeyCreate
        :param integration_id: Optional[UUID]
        :return: tuple[ApiKey, str]
        """
        # Generate a random API key
        api_key = secrets.token_urlsafe(settings.API_KEY_LENGTH)
        # Use SHA256 for API keys (deterministic, allows direct lookup)
        key_hash = self._hash_api_key(api_key)
        
        # Create API key record
        api_key_record = ApiKey(
            user_id=user_id,
            integration_id=integration_id,
            key_hash=key_hash,
            name=api_key_data.name,
            expires_at=api_key_data.expires_at,
        )
        
        created_key = await self.auth_repository.create_api_key(api_key_record)
        return created_key, api_key

    async def verify_api_key(self, api_key: str) -> Optional[User]:
        """
        Verify an API key and return the associated user.
        :param api_key: str
        :return: Optional[User]
        """
        # Hash the provided key using SHA256 (deterministic)
        key_hash = self._hash_api_key(api_key)
        
        # Find the API key record
        api_key_record = await self.auth_repository.get_api_key_by_hash(key_hash)
        if not api_key_record:
            return None
        
        # Check if expired
        if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
            return None
        
        # Update last used timestamp
        await self.auth_repository.update_api_key_last_used(api_key_record.id)
        
        # Get the user
        return await self.auth_repository.get_user_by_id(api_key_record.user_id)

    async def verify_api_key_and_get_context(
        self, api_key: str
    ) -> Optional[tuple[User, Optional[UUID]]]:
        """
        Verify an API key and return (user, integration_id). integration_id is None for personal keys.
        :param api_key: str
        :return: Optional[tuple[User, Optional[UUID]]]
        """
        key_hash = self._hash_api_key(api_key)
        api_key_record = await self.auth_repository.get_api_key_by_hash(key_hash)
        if not api_key_record:
            return None
        if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
            return None
        await self.auth_repository.update_api_key_last_used(api_key_record.id)
        user = await self.auth_repository.get_user_by_id(api_key_record.user_id)
        if not user or not user.is_active:
            return None
        return (user, api_key_record.integration_id)

    async def get_user_api_keys(self, user_id: UUID) -> list[ApiKey]:
        """
        Get all API keys for a user.
        :param user_id: UUID
        :return: list[ApiKey]
        """
        return await self.auth_repository.get_api_keys_by_user_id(user_id)

    async def delete_api_key(self, user_id: UUID, key_id: UUID) -> bool:
        """
        Delete an API key (only if owned by user).
        :param user_id: UUID
        :param key_id: UUID
        :return: bool
        """
        api_key = await self.auth_repository.get_api_key_by_id(key_id)
        if not api_key or api_key.user_id != user_id:
            return False
        return await self.auth_repository.delete_api_key(key_id)

    async def delete_api_key_for_integration(
        self, user_id: UUID, integration_id: UUID, key_id: UUID
    ) -> bool:
        """
        Delete an API key only if owned by user and tied to the given integration.
        :param user_id: UUID
        :param integration_id: UUID
        :param key_id: UUID
        :return: bool
        """
        api_key = await self.auth_repository.get_api_key_by_id(key_id)
        if (
            not api_key
            or api_key.user_id != user_id
            or api_key.integration_id != integration_id
        ):
            return False
        return await self.auth_repository.delete_api_key(key_id)

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """
        Get a user by ID.
        :param user_id: UUID
        :return: Optional[User]
        """
        return await self.auth_repository.get_user_by_id(user_id)