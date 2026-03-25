import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class GrantType(StrEnum):
    welcome = "grant_welcome"
    promotional = "grant_promotional"
    reward = "grant_reward"


class WalletResponse(BaseModel):
    """Wallet detail with current balance."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    agent_id: uuid.UUID | None = None
    wallet_type: str
    balance: int
    created_at: datetime
    updated_at: datetime


class WalletSummary(BaseModel):
    """Balance breakdown by credit source."""

    wallet_id: uuid.UUID
    balance: int
    total_granted: int = 0
    total_purchased: int = 0
    total_earned: int = 0
    total_spent: int = 0
    transaction_count: int = 0


class TransactionResponse(BaseModel):
    """A single ledger entry."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    wallet_id: uuid.UUID
    amount: int
    tx_type: str
    reference_id: uuid.UUID | None
    description: str | None
    created_at: datetime


class TransferRequest(BaseModel):
    """Request to transfer credits between two wallets."""

    from_wallet_id: uuid.UUID
    to_wallet_id: uuid.UUID
    amount: int = Field(..., gt=0)
    description: str | None = None


class CreditDebitRequest(BaseModel):
    """Request to credit or debit a wallet (admin / simulator action)."""

    amount: int = Field(..., gt=0)
    description: str | None = None


class GrantRequest(BaseModel):
    """Request to grant credits to a wallet."""

    amount: int = Field(..., gt=0)
    grant_type: GrantType = GrantType.promotional
    description: str | None = None


class ConsolidateRequest(BaseModel):
    """Request to sweep agent wallet balances into the user wallet."""

    agent_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Agent IDs to sweep. None = sweep all agent wallets.",
    )


class ConsolidateResponse(BaseModel):
    """Result of a consolidation sweep."""

    reference_id: uuid.UUID
    total_swept: int
    wallets_swept: int


class AgentWalletSummary(BaseModel):
    """Compact view of an agent wallet for the overview endpoint."""

    model_config = {"from_attributes": True}

    wallet_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str | None = None
    balance: int


class UserWalletOverview(BaseModel):
    """User wallet plus all associated agent wallet summaries."""

    wallet: WalletResponse
    agent_wallets: list[AgentWalletSummary] = Field(default_factory=list)
    total_agent_balance: int = 0


class CreditPackageResponse(BaseModel):
    """A purchasable credit package."""

    id: str
    credits: int
    price_cents: int
    label: str


class PurchaseRequest(BaseModel):
    """Request to initiate a credit purchase."""

    package_id: str


class PurchaseResponse(BaseModel):
    """Status of a credit purchase."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    wallet_id: uuid.UUID
    package_id: str
    credits_amount: int
    price_cents: int
    status: str
    provider_reference: str | None
    created_at: datetime
    updated_at: datetime
