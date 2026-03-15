"""Brand service."""

import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import Depends

from src.core.settings import settings
from src.exceptions import ForbiddenException, RateLimitException
from src.models.brand import Brand
from src.repositories.brand import BrandRepository
from src.schemas.brand import BrandCreate, BrandUpdate
from src.utilities.email import send_brand_verification_code


def _generate_code(length: int = 6) -> str:
    """Generate a numeric verification code."""
    return "".join(secrets.choice("0123456789") for _ in range(length))


class BrandService:
    """Service for brand operations."""

    RESEND_COOLDOWN_MINUTES = 2

    def __init__(self, brand_repository: BrandRepository = Depends()):
        self.brand_repository = brand_repository

    async def create(self, owner_id: UUID, data: BrandCreate) -> Brand:
        """
        Create a new brand.
        :param owner_id: UUID
        :param data: BrandCreate
        :return: Brand
        """
        existing = await self.brand_repository.get_by_slug(data.slug)
        if existing:
            raise ValueError(f"Brand with slug '{data.slug}' already exists")

        brand = Brand(
            owner_id=owner_id,
            name=data.name,
            slug=data.slug.strip().lower(),
            description=data.description,
            website=data.website,
            logo_url=data.logo_url,
            verification_email=data.verification_email,
            verification_status="pending",
        )
        return await self.brand_repository.create(brand)

    async def get_by_id(self, brand_id: UUID) -> Optional[Brand]:
        """
        Get brand by ID.
        :param brand_id: UUID
        :return: Optional[Brand]
        """
        return await self.brand_repository.get_by_id(brand_id)

    async def get_by_slug(self, slug: str) -> Optional[Brand]:
        """
        Get brand by slug.
        :param slug: str
        :return: Optional[Brand]
        """
        return await self.brand_repository.get_by_slug(slug)

    async def get_by_id_or_slug(self, id_or_slug: str) -> Optional[Brand]:
        """
        Get brand by UUID string or slug.
        :param id_or_slug: str
        :return: Optional[Brand]
        """
        try:
            uid = UUID(id_or_slug)
            return await self.brand_repository.get_by_id(uid)
        except ValueError:
            return await self.brand_repository.get_by_slug(id_or_slug)

    async def list_by_owner(self, owner_id: UUID) -> List[Brand]:
        """
        List brands owned by user.
        :param owner_id: UUID
        :return: List[Brand]
        """
        return await self.brand_repository.get_by_owner_id(owner_id)

    async def update(self, brand: Brand, data: BrandUpdate) -> Brand:
        """
        Update brand.
        :param brand: Brand
        :param data: BrandUpdate
        :return: Brand
        """
        if data.name is not None:
            brand.name = data.name
        if data.slug is not None:
            existing = await self.brand_repository.get_by_slug(data.slug)
            if existing and existing.id != brand.id:
                raise ValueError(f"Brand with slug '{data.slug}' already exists")
            brand.slug = data.slug.strip().lower()
        if data.description is not None:
            brand.description = data.description
        if data.website is not None:
            brand.website = data.website
        if data.logo_url is not None:
            brand.logo_url = data.logo_url
        if data.verification_email is not None:
            brand.verification_email = data.verification_email
        if data.brand_details is not None:
            brand.brand_details = data.brand_details
        return await self.brand_repository.update(brand)

    async def delete(self, brand_id: UUID, owner_id: UUID) -> None:
        """
        Delete a brand. Owner only.
        :param brand_id: UUID
        :param owner_id: UUID
        """
        brand = await self.brand_repository.get_by_id(brand_id)
        if not brand:
            raise ValueError("Brand not found")
        if brand.owner_id != owner_id:
            raise ForbiddenException("Not the brand owner")
        await self.brand_repository.delete(brand)

    def _resend_cooldown_ok(self, brand: Brand) -> bool:
        """
        Return True if enough time has passed since last send.
        :param brand: Brand
        :return: bool
        """
        if not brand.verification_code_expires_at:
            return True
        # Code was sent at expires_at - expiry_minutes
        sent_at = brand.verification_code_expires_at - timedelta(
            minutes=settings.BRAND_VERIFICATION_CODE_EXPIRY_MINUTES
        )
        return datetime.now(timezone.utc) - sent_at > timedelta(
            minutes=self.RESEND_COOLDOWN_MINUTES
        )

    async def send_verification_code(self, brand_id: UUID, owner_id: UUID) -> Brand:
        """
        Generate code, set expiry, send email (skeleton). Rate-limited.
        :param brand_id: UUID
        :param owner_id: UUID
        :return: Brand
        """
        brand = await self.brand_repository.get_by_id(brand_id)
        if not brand:
            raise ValueError("Brand not found")
        if brand.owner_id != owner_id:
            raise ForbiddenException("Not the brand owner")
        if not brand.verification_email:
            raise ValueError("Brand has no verification email set")

        if not self._resend_cooldown_ok(brand):
            raise RateLimitException("Please wait before requesting another code")

        code = _generate_code(6)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.BRAND_VERIFICATION_CODE_EXPIRY_MINUTES
        )
        brand.verification_code = code
        brand.verification_code_expires_at = expires_at
        brand.verification_status = "pending"
        await self.brand_repository.update(brand)

        try:
            await send_brand_verification_code(
                to_email=brand.verification_email,
                code=code,
                expires_at=expires_at,
            )
        except Exception as exc:
            # Roll back the code so the user can retry cleanly
            brand.verification_code = None
            brand.verification_code_expires_at = None
            brand.verification_status = "pending"
            await self.brand_repository.update(brand)
            raise ValueError("Failed to send verification email. Please try again.") from exc
        return brand

    async def verify_code(self, brand_id: UUID, code: str, owner_id: UUID) -> Brand:
        """Check code and mark verified if valid.
        :param brand_id: UUID
        :param code: str
        :param owner_id: UUID
        :return: Brand
        """
        brand = await self.brand_repository.get_by_id(brand_id)
        if not brand:
            raise ValueError("Brand not found")
        if brand.owner_id != owner_id:
            raise ForbiddenException("Not the brand owner")

        now = datetime.now(timezone.utc)
        if not brand.verification_code or brand.verification_code != code.strip():
            brand.verification_status = "failed"
            await self.brand_repository.update(brand)
            raise ValueError("Invalid or expired code")
        if brand.verification_code_expires_at and now > brand.verification_code_expires_at:
            brand.verification_status = "failed"
            await self.brand_repository.update(brand)
            raise ValueError("Invalid or expired code")

        brand.verification_status = "verified"
        brand.verified_at = now
        brand.verification_code = None
        brand.verification_code_expires_at = None
        await self.brand_repository.update(brand)
        return brand
