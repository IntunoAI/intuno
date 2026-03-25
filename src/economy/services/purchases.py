import uuid

from fastapi import Depends, HTTPException

from src.core.settings import settings
from src.economy.models.credit_purchase import CreditPurchase
from src.economy.models.wallet import Transaction
from src.economy.repositories.purchases import PurchaseRepository
from src.economy.repositories.wallets import WalletRepository
from src.economy.schemas.wallet import (
    CreditPackageResponse,
    PurchaseResponse,
)


class PurchaseService:
    """Handles the credit purchase lifecycle.

    Simulates a Stripe-like flow: the caller picks a package, we create a
    pending purchase with a fake provider reference, and a separate
    ``confirm`` call finalises it (standing in for a webhook).
    """

    def __init__(
        self,
        purchase_repository: PurchaseRepository = Depends(),
        wallet_repository: WalletRepository = Depends(),
    ):
        self.purchase_repository = purchase_repository
        self.wallet_repository = wallet_repository

    def list_packages(self) -> list[CreditPackageResponse]:
        return [CreditPackageResponse(**pkg) for pkg in settings.ECONOMY_CREDIT_PACKAGES]

    async def create_purchase(
        self,
        wallet_id: uuid.UUID,
        package_id: str,
    ) -> PurchaseResponse:
        """Initiate a purchase in ``pending`` status."""
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        package = self._resolve_package(package_id)

        provider_ref = f"sim_pi_{uuid.uuid4().hex[:16]}"

        purchase = CreditPurchase(
            wallet_id=wallet_id,
            package_id=package_id,
            credits_amount=package["credits"],
            price_cents=package["price_cents"],
            status="pending",
            provider_reference=provider_ref,
        )
        purchase = await self.purchase_repository.create(purchase)
        return PurchaseResponse.model_validate(purchase)

    async def confirm_purchase(self, purchase_id: uuid.UUID) -> PurchaseResponse:
        """Mark a pending purchase as completed and credit the wallet."""
        purchase = await self.purchase_repository.get_by_id(purchase_id)
        if not purchase:
            raise HTTPException(status_code=404, detail="Purchase not found")
        if purchase.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Purchase is '{purchase.status}', expected 'pending'",
            )

        wallet = await self.wallet_repository.get_by_id(purchase.wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        new_balance = wallet.balance + purchase.credits_amount
        await self.wallet_repository.update_balance(wallet.id, new_balance)

        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=wallet.id,
                amount=purchase.credits_amount,
                tx_type="purchase",
                reference_id=purchase.id,
                description=f"Purchased {purchase.credits_amount} credits ({purchase.package_id} package)",
            )
        )

        await self.purchase_repository.update_status(purchase_id, "completed")
        purchase = await self.purchase_repository.get_by_id(purchase_id)
        return PurchaseResponse.model_validate(purchase)

    async def cancel_purchase(self, purchase_id: uuid.UUID) -> PurchaseResponse:
        """Cancel a pending purchase."""
        purchase = await self.purchase_repository.get_by_id(purchase_id)
        if not purchase:
            raise HTTPException(status_code=404, detail="Purchase not found")
        if purchase.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"Purchase is '{purchase.status}', expected 'pending'",
            )

        await self.purchase_repository.update_status(purchase_id, "failed")
        purchase = await self.purchase_repository.get_by_id(purchase_id)
        return PurchaseResponse.model_validate(purchase)

    def _resolve_package(self, package_id: str) -> dict:
        for pkg in settings.ECONOMY_CREDIT_PACKAGES:
            if pkg["id"] == package_id:
                return pkg
        raise HTTPException(
            status_code=400,
            detail=f"Unknown package '{package_id}'. Use GET /credits/packages to see options.",
        )
