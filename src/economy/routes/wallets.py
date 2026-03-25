import uuid

from fastapi import APIRouter, Depends, Query

from src.core.auth import get_current_user
from src.models.auth import User
from src.economy.schemas.wallet import (
    CreditDebitRequest,
    GrantRequest,
    TransactionResponse,
    TransferRequest,
    WalletResponse,
    WalletSummary,
)
from src.economy.services.wallets import WalletService

router = APIRouter()


@router.get("", response_model=list[WalletResponse])
async def list_wallets(
    wallet_service: WalletService = Depends(),
    limit: int = Query(100, ge=1, le=200),
) -> list[WalletResponse]:
    """List all wallets ordered by balance."""
    return await wallet_service.list_wallets(limit=limit)


@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: uuid.UUID,
    wallet_service: WalletService = Depends(),
) -> WalletResponse:
    """Retrieve a wallet by its ID."""
    return await wallet_service.get_wallet(wallet_id)


@router.get("/agent/{agent_id}", response_model=WalletResponse)
async def get_wallet_by_agent(
    agent_id: uuid.UUID,
    wallet_service: WalletService = Depends(),
) -> WalletResponse:
    """Retrieve the wallet for a given agent."""
    return await wallet_service.get_wallet_by_agent(agent_id)


@router.post("/{wallet_id}/credit", response_model=WalletResponse)
async def credit_wallet(
    wallet_id: uuid.UUID,
    payload: CreditDebitRequest,
    _user: User = Depends(get_current_user),
    wallet_service: WalletService = Depends(),
) -> WalletResponse:
    """Add credits to a wallet."""
    return await wallet_service.credit(wallet_id, payload)


@router.post("/{wallet_id}/debit", response_model=WalletResponse)
async def debit_wallet(
    wallet_id: uuid.UUID,
    payload: CreditDebitRequest,
    _user: User = Depends(get_current_user),
    wallet_service: WalletService = Depends(),
) -> WalletResponse:
    """Remove credits from a wallet."""
    return await wallet_service.debit(wallet_id, payload)


@router.post("/transfer", response_model=dict)
async def transfer_credits(
    payload: TransferRequest,
    _user: User = Depends(get_current_user),
    wallet_service: WalletService = Depends(),
) -> dict:
    """Transfer credits between two wallets."""
    return await wallet_service.transfer(payload)


@router.post("/{wallet_id}/grant", response_model=WalletResponse)
async def grant_credits(
    wallet_id: uuid.UUID,
    payload: GrantRequest,
    wallet_service: WalletService = Depends(),
) -> WalletResponse:
    """Grant credits to a wallet (welcome, promotional, or reward)."""
    return await wallet_service.grant_credits(wallet_id, payload)


@router.get("/{wallet_id}/summary", response_model=WalletSummary)
async def get_wallet_summary(
    wallet_id: uuid.UUID,
    wallet_service: WalletService = Depends(),
) -> WalletSummary:
    """Return balance breakdown by credit source."""
    return await wallet_service.get_wallet_summary(wallet_id)


@router.get("/{wallet_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    wallet_id: uuid.UUID,
    wallet_service: WalletService = Depends(),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[TransactionResponse]:
    """List ledger entries for a wallet."""
    return await wallet_service.list_transactions(
        wallet_id, limit=limit, offset=offset,
    )
