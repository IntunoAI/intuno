"""Brand routes."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.auth import get_current_user
from src.exceptions import BadRequestException, ForbiddenException, NotFoundException
from src.models.auth import User
from src.schemas.brand import (
    BrandCreate,
    BrandResponse,
    BrandUpdate,
    VerifyBrandRequest,
    VerifyBrandResponse,
)
from src.services.brand import BrandService

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.post("", response_model=BrandResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(
    data: BrandCreate,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> BrandResponse:
    """Create a new brand (claim brand)."""
    try:
        brand = await brand_service.create(current_user.id, data)
        return brand
    except ValueError as e:
        raise BadRequestException(str(e))


@router.get("/me", response_model=List[BrandResponse])
async def list_my_brands(
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> List[BrandResponse]:
    """List current user's brands."""
    brands = await brand_service.list_by_owner(current_user.id)
    return brands


@router.get("/{id_or_slug}", response_model=BrandResponse)
async def get_brand(
    id_or_slug: str,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> BrandResponse:
    """Get brand by ID or slug."""
    brand = await brand_service.get_by_id_or_slug(id_or_slug)
    if not brand:
        raise NotFoundException("Brand")
    if brand.owner_id != current_user.id:
        raise NotFoundException("Brand")
    return brand


@router.put("/{brand_id}", response_model=BrandResponse)
async def update_brand(
    brand_id: UUID,
    data: BrandUpdate,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> BrandResponse:
    """Update brand (wizard steps). Owner only."""
    brand = await brand_service.get_by_id(brand_id)
    if not brand:
        raise NotFoundException("Brand")
    if brand.owner_id != current_user.id:
        raise ForbiddenException("Not the brand owner")
    try:
        brand = await brand_service.update(brand, data)
        return brand
    except ValueError as e:
        raise BadRequestException(str(e))


@router.post("/{brand_id}/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
async def resend_verification(
    brand_id: UUID,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> None:
    """Send or resend verification code. Owner only. Rate-limited."""
    try:
        await brand_service.send_verification_code(brand_id, current_user.id)
    except ValueError as e:
        raise BadRequestException(str(e))
    except HTTPException:
        raise


@router.post("/{brand_id}/verify", response_model=VerifyBrandResponse)
async def verify_brand(
    brand_id: UUID,
    body: VerifyBrandRequest,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> VerifyBrandResponse:
    """Submit verification code. Owner only."""
    try:
        brand = await brand_service.verify_code(
            brand_id, body.code, current_user.id
        )
        return VerifyBrandResponse(
            success=True,
            verification_status=brand.verification_status,
        )
    except ValueError as e:
        raise BadRequestException(str(e))
    except HTTPException:
        raise
