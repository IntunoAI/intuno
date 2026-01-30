"""Brand schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class BrandCreate(BaseModel):
    """Brand creation (wizard) schema."""

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    verification_email: Optional[EmailStr] = None


class BrandUpdate(BaseModel):
    """Brand update (wizard steps) schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    verification_email: Optional[EmailStr] = None


class BrandResponse(BaseModel):
    """Brand response schema."""

    id: UUID
    owner_id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    verification_email: Optional[str] = None
    verification_status: str
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class VerifyBrandRequest(BaseModel):
    """Request body for submitting verification code."""

    code: str = Field(..., min_length=1)


class VerifyBrandResponse(BaseModel):
    """Response after verify code submission."""

    success: bool
    verification_status: str
