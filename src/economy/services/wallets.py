import uuid

from fastapi import Depends, HTTPException

from src.economy.models.wallet import Transaction
from src.economy.repositories.wallets import WalletRepository
from src.economy.schemas.wallet import (
    CreditDebitRequest,
    GrantRequest,
    TransactionResponse,
    TransferRequest,
    WalletResponse,
    WalletSummary,
)


class WalletService:
    """Handles wallet business logic including transfers and ledger entries.

    Every transfer uses double-entry bookkeeping: a debit on the source
    wallet and a credit on the destination wallet share the same reference_id.
    """

    def __init__(self, wallet_repository: WalletRepository = Depends()):
        self.wallet_repository = wallet_repository

    async def get_wallet(self, wallet_id: uuid.UUID) -> WalletResponse:
        """Fetch a single wallet or raise 404."""
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        return WalletResponse.model_validate(wallet)

    async def get_wallet_by_agent(self, agent_id: uuid.UUID) -> WalletResponse:
        """Fetch the wallet belonging to an agent."""
        wallet = await self.wallet_repository.get_by_agent_id(agent_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found for agent")
        return WalletResponse.model_validate(wallet)

    async def list_wallets(self, limit: int = 100) -> list[WalletResponse]:
        """Return all wallets ordered by balance."""
        wallets = await self.wallet_repository.list_all_wallets(limit=limit)
        return [WalletResponse.model_validate(w) for w in wallets]

    async def credit(
        self,
        wallet_id: uuid.UUID,
        payload: CreditDebitRequest,
    ) -> WalletResponse:
        """Add credits to a wallet."""
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        new_balance = wallet.balance + payload.amount
        await self.wallet_repository.update_balance(wallet_id, new_balance)

        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=wallet_id,
                amount=payload.amount,
                tx_type="credit",
                description=payload.description or "Manual credit",
            )
        )
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        return WalletResponse.model_validate(wallet)

    async def debit(
        self,
        wallet_id: uuid.UUID,
        payload: CreditDebitRequest,
    ) -> WalletResponse:
        """Remove credits from a wallet."""
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")
        if wallet.balance < payload.amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        new_balance = wallet.balance - payload.amount
        await self.wallet_repository.update_balance(wallet_id, new_balance)

        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=wallet_id,
                amount=-payload.amount,
                tx_type="debit",
                description=payload.description or "Manual debit",
            )
        )
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        return WalletResponse.model_validate(wallet)

    async def transfer(self, payload: TransferRequest) -> dict:
        """Transfer credits between two wallets with double-entry bookkeeping."""
        source = await self.wallet_repository.get_by_id(payload.from_wallet_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source wallet not found")
        destination = await self.wallet_repository.get_by_id(payload.to_wallet_id)
        if not destination:
            raise HTTPException(status_code=404, detail="Destination wallet not found")
        if source.balance < payload.amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")

        reference_id = uuid.uuid4()
        description = payload.description or "Transfer"

        await self.wallet_repository.update_balance(
            source.id, source.balance - payload.amount,
        )
        await self.wallet_repository.update_balance(
            destination.id, destination.balance + payload.amount,
        )

        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=source.id,
                amount=-payload.amount,
                tx_type="transfer_out",
                reference_id=reference_id,
                description=description,
            )
        )
        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=destination.id,
                amount=payload.amount,
                tx_type="transfer_in",
                reference_id=reference_id,
                description=description,
            )
        )

        return {
            "reference_id": reference_id,
            "from_wallet_id": source.id,
            "to_wallet_id": destination.id,
            "amount": payload.amount,
        }

    async def grant_credits(
        self,
        wallet_id: uuid.UUID,
        payload: GrantRequest,
    ) -> WalletResponse:
        """Grant credits to a wallet (welcome bonus, promotional, reward)."""
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        new_balance = wallet.balance + payload.amount
        await self.wallet_repository.update_balance(wallet_id, new_balance)

        await self.wallet_repository.create_transaction(
            Transaction(
                wallet_id=wallet_id,
                amount=payload.amount,
                tx_type=payload.grant_type.value,
                description=payload.description or f"{payload.grant_type.name.replace('_', ' ').title()} grant",
            )
        )
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        return WalletResponse.model_validate(wallet)

    async def get_wallet_summary(self, wallet_id: uuid.UUID) -> WalletSummary:
        """Return a balance breakdown by credit source."""
        wallet = await self.wallet_repository.get_by_id(wallet_id)
        if not wallet:
            raise HTTPException(status_code=404, detail="Wallet not found")

        summary = await self.wallet_repository.get_transaction_summary(wallet_id)
        return WalletSummary(
            wallet_id=wallet_id,
            balance=wallet.balance,
            **summary,
        )

    async def list_transactions(
        self,
        wallet_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TransactionResponse]:
        """Return ledger entries for a wallet."""
        transactions = await self.wallet_repository.list_transactions(
            wallet_id, limit=limit, offset=offset,
        )
        return [TransactionResponse.model_validate(t) for t in transactions]
