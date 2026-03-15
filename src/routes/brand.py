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
from src.services.registry import RegistryService

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.post(
    "",
    response_model=BrandResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_brand(
    data: BrandCreate,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> BrandResponse:
    """
    Create a new brand (claim brand).
    :param data: BrandCreate
    :param current_user: User
    :param brand_service: BrandService
    :return: BrandResponse
    """
    try:
        brand = await brand_service.create(current_user.id, data)
        return brand
    except ValueError as e:
        raise BadRequestException(str(e))


@router.get(
    "/me",
    response_model=List[BrandResponse],
)
async def list_my_brands(
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> List[BrandResponse]:
    """
    List current user's brands.
    :param current_user: User
    :param brand_service: BrandService
    :return: List[BrandResponse]
    """
    brands = await brand_service.list_by_owner(current_user.id)
    return brands


@router.get(
    "/{id_or_slug}",
    response_model=BrandResponse,
)
async def get_brand(
    id_or_slug: str,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> BrandResponse:
    """
    Get brand by ID or slug.
    :param id_or_slug: str
    :param current_user: User
    :param brand_service: BrandService
    :return: BrandResponse
    """
    brand = await brand_service.get_by_id_or_slug(id_or_slug)
    if not brand:
        raise NotFoundException("Brand")
    if brand.owner_id != current_user.id:
        raise NotFoundException("Brand")
    return brand


@router.put(
    "/{brand_id}",
    response_model=BrandResponse,
)
async def update_brand(
    brand_id: UUID,
    data: BrandUpdate,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> BrandResponse:
    """
    Update brand (wizard steps). Owner only.
    :param brand_id: UUID
    :param data: BrandUpdate
    :param current_user: User
    :param brand_service: BrandService
    :return: BrandResponse
    """
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


@router.delete(
    "/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_brand(
    brand_id: UUID,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> None:
    """
    Delete a brand. Owner only.
    :param brand_id: UUID
    :param current_user: User
    :param brand_service: BrandService
    """
    try:
        await brand_service.delete(brand_id, current_user.id)
    except ValueError as e:
        raise BadRequestException(str(e))
    except ForbiddenException:
        raise


@router.post(
    "/{brand_id}/resend-verification",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def resend_verification(
    brand_id: UUID,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
) -> None:
    """
    Send or resend verification code. Owner only. Rate-limited.
    :param brand_id: UUID
    :param current_user: User
    :param brand_service: BrandService
    :return: None
    """
    try:
        await brand_service.send_verification_code(brand_id, current_user.id)
    except ValueError as e:
        raise BadRequestException(str(e))
    except HTTPException:
        raise


@router.post(
    "/{brand_id}/verify",
    response_model=VerifyBrandResponse,
)
async def verify_brand(
    brand_id: UUID,
    body: VerifyBrandRequest,
    current_user: User = Depends(get_current_user),
    brand_service: BrandService = Depends(),
    registry_service: RegistryService = Depends(),
) -> VerifyBrandResponse:
    """
    Submit verification code. Owner only. Creates brand agent on successful verification.
    :param brand_id: UUID
    :param body: VerifyBrandRequest
    :param current_user: User
    :param brand_service: BrandService
    :param registry_service: RegistryService
    :return: VerifyBrandResponse
    """
    try:
        brand = await brand_service.verify_code(
            brand_id, body.code, current_user.id
        )
        if brand.verification_status == "verified":
            try:
                await registry_service.create_brand_agent(brand)
            except Exception:
                pass  # Non-blocking; brand verification succeeded
        return VerifyBrandResponse(
            success=True,
            verification_status=brand.verification_status,
        )
    except ValueError as e:
        raise BadRequestException(str(e))
    except HTTPException:
        raise
