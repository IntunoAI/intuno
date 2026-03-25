import uuid

from fastapi import APIRouter, Depends

from src.economy.schemas.wallet import (
    CreditPackageResponse,
    PurchaseRequest,
    PurchaseResponse,
)
from src.economy.services.purchases import PurchaseService

router = APIRouter()


@router.get("/packages", response_model=list[CreditPackageResponse])
async def list_packages(
    purchase_service: PurchaseService = Depends(),
) -> list[CreditPackageResponse]:
    """List available credit packages for purchase."""
    return purchase_service.list_packages()


@router.post("/wallets/{wallet_id}/purchase", response_model=PurchaseResponse)
async def create_purchase(
    wallet_id: uuid.UUID,
    payload: PurchaseRequest,
    purchase_service: PurchaseService = Depends(),
) -> PurchaseResponse:
    """Initiate a credit purchase. Returns a pending purchase with a simulated provider reference."""
    return await purchase_service.create_purchase(wallet_id, payload.package_id)


@router.post("/purchases/{purchase_id}/confirm", response_model=PurchaseResponse)
async def confirm_purchase(
    purchase_id: uuid.UUID,
    purchase_service: PurchaseService = Depends(),
) -> PurchaseResponse:
    """Confirm a pending purchase (simulates Stripe webhook). Credits are added to the wallet."""
    return await purchase_service.confirm_purchase(purchase_id)


@router.post("/purchases/{purchase_id}/cancel", response_model=PurchaseResponse)
async def cancel_purchase(
    purchase_id: uuid.UUID,
    purchase_service: PurchaseService = Depends(),
) -> PurchaseResponse:
    """Cancel a pending purchase."""
    return await purchase_service.cancel_purchase(purchase_id)
