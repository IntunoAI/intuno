"""Auth domain schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class UserRegister(BaseModel):
    """User registration schema."""
    
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserLogin(BaseModel):
    """User login schema."""
    
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Token response schema."""
    
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApiKeyCreate(BaseModel):
    """API key creation schema."""
    
    name: str
    expires_at: Optional[datetime] = None


class ApiKeyResponse(BaseModel):
    """API key response schema."""
    
    id: UUID
    name: str
    key: str  # Only returned on creation
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class ApiKeyListResponse(BaseModel):
    """API key list response schema."""
    
    id: UUID
    name: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class UserResponse(BaseModel):
    """User response schema."""
    
    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime