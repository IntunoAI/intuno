"""Auth domain service."""

import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import settings
from src.models.auth import ApiKey, User
from src.repositories.auth import AuthRepository
from src.schemas.auth import ApiKeyCreate, UserLogin, UserRegister

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = AuthRepository(session)

    def hash_password(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, user_id: UUID) -> str:
        """Create a JWT access token."""
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
        to_encode = {
            "sub": str(user_id),
            "exp": expire,
            "type": "access"
        }
        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[UUID]:
        """Verify a JWT token and return user ID."""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                return None
            return UUID(user_id)
        except (JWTError, ValueError):
            return None

    async def register_user(self, user_data: UserRegister) -> User:
        """Register a new user."""
        # Check if user already exists
        existing_user = await self.repository.get_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        # Create new user
        user = User(
            email=user_data.email,
            password_hash=self.hash_password(user_data.password),
            first_name=user_data.first_name,
            last_name=user_data.last_name,
        )
        return await self.repository.create_user(user)

    async def authenticate_user(self, login_data: UserLogin) -> Optional[User]:
        """Authenticate a user with email and password."""
        user = await self.repository.get_user_by_email(login_data.email)
        if not user or not self.verify_password(login_data.password, user.password_hash):
            return None
        return user

    async def create_api_key(self, user_id: UUID, api_key_data: ApiKeyCreate) -> tuple[ApiKey, str]:
        """Create a new API key for a user."""
        # Generate a random API key
        api_key = secrets.token_urlsafe(settings.API_KEY_LENGTH)
        key_hash = self.hash_password(api_key)
        
        # Create API key record
        api_key_record = ApiKey(
            user_id=user_id,
            key_hash=key_hash,
            name=api_key_data.name,
            expires_at=api_key_data.expires_at,
        )
        
        created_key = await self.repository.create_api_key(api_key_record)
        return created_key, api_key

    async def verify_api_key(self, api_key: str) -> Optional[User]:
        """Verify an API key and return the associated user."""
        # Hash the provided key to compare with stored hash
        key_hash = self.hash_password(api_key)
        
        # Find the API key record
        api_key_record = await self.repository.get_api_key_by_hash(key_hash)
        if not api_key_record:
            return None
        
        # Check if expired
        if api_key_record.expires_at and api_key_record.expires_at < datetime.utcnow():
            return None
        
        # Update last used timestamp
        await self.repository.update_api_key_last_used(api_key_record.id)
        
        # Get the user
        return await self.repository.get_user_by_id(api_key_record.user_id)

    async def get_user_api_keys(self, user_id: UUID) -> list[ApiKey]:
        """Get all API keys for a user."""
        return await self.repository.get_api_keys_by_user_id(user_id)

    async def delete_api_key(self, user_id: UUID, key_id: UUID) -> bool:
        """Delete an API key (only if owned by user)."""
        api_key = await self.repository.get_api_key_by_id(key_id)
        if not api_key or api_key.user_id != user_id:
            return False
        return await self.repository.delete_api_key(key_id)