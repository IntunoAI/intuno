import uuid

from fastapi import Depends
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.economy.models.wallet import Wallet, Transaction
from src.models.registry import Agent


class WalletRepository:
    """Persistence layer for wallet and transaction records."""

    def __init__(self, db_session: AsyncSession = Depends(get_db)):
        self.db_session = db_session

    async def create(self, wallet: Wallet) -> Wallet:
        """Insert a new wallet and return the persisted instance."""
        self.db_session.add(wallet)
        await self.db_session.flush()
        await self.db_session.refresh(wallet)
        return wallet

    async def get_by_id(self, wallet_id: uuid.UUID) -> Wallet | None:
        """Return a wallet by primary key, or None."""
        result = await self.db_session.execute(
            select(Wallet).where(Wallet.id == wallet_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> Wallet | None:
        """Return the user-level wallet for a given user."""
        result = await self.db_session.execute(
            select(Wallet).where(
                Wallet.user_id == user_id,
                Wallet.wallet_type == "user",
            )
        )
        return result.scalar_one_or_none()

    async def get_by_agent_id(self, agent_id: uuid.UUID) -> Wallet | None:
        """Return the agent-level wallet for a specific agent."""
        result = await self.db_session.execute(
            select(Wallet).where(
                Wallet.agent_id == agent_id,
                Wallet.wallet_type == "agent",
            )
        )
        return result.scalar_one_or_none()

    async def get_agent_wallets_for_user(
        self,
        user_id: uuid.UUID,
        agent_ids: list[uuid.UUID] | None = None,
    ) -> list[Wallet]:
        """Return all agent wallets owned by a user (via agents table)."""
        stmt = (
            select(Wallet)
            .join(Agent, Wallet.agent_id == Agent.id)
            .where(Agent.user_id == user_id, Wallet.wallet_type == "agent")
        )
        if agent_ids:
            stmt = stmt.where(Wallet.agent_id.in_(agent_ids))
        result = await self.db_session.execute(stmt)
        return list(result.scalars().all())

    async def update_balance(self, wallet_id: uuid.UUID, new_balance: int) -> None:
        """Set the wallet balance to an exact value."""
        await self.db_session.execute(
            update(Wallet).where(Wallet.id == wallet_id).values(balance=new_balance)
        )

    async def atomic_debit(self, wallet_id: uuid.UUID, amount: int) -> bool:
        """Atomically debit *amount* credits if balance is sufficient.

        Returns True if the debit succeeded, False if insufficient funds.
        """
        result = await self.db_session.execute(
            update(Wallet)
            .where(Wallet.id == wallet_id, Wallet.balance >= amount)
            .values(balance=Wallet.balance - amount)
        )
        return result.rowcount == 1

    async def atomic_credit(self, wallet_id: uuid.UUID, amount: int) -> None:
        """Atomically credit *amount* credits to a wallet."""
        await self.db_session.execute(
            update(Wallet)
            .where(Wallet.id == wallet_id)
            .values(balance=Wallet.balance + amount)
        )

    async def create_transaction(self, transaction: Transaction) -> Transaction:
        """Insert a ledger entry and return it."""
        self.db_session.add(transaction)
        await self.db_session.flush()
        await self.db_session.refresh(transaction)
        return transaction

    async def list_transactions(
        self,
        wallet_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Transaction]:
        """Return recent transactions for a wallet, newest first."""
        result = await self.db_session.execute(
            select(Transaction)
            .where(Transaction.wallet_id == wallet_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all_wallets(self, limit: int = 100) -> list[Wallet]:
        """Return all wallets, ordered by balance descending."""
        result = await self.db_session.execute(
            select(Wallet).order_by(Wallet.balance.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_transaction_summary(self, wallet_id: uuid.UUID) -> dict:
        """Aggregate transaction amounts grouped by category for a wallet."""
        granted = func.coalesce(
            func.sum(
                case(
                    (Transaction.tx_type.like("grant_%"), Transaction.amount),
                    (Transaction.tx_type == "welcome_grant", Transaction.amount),
                    else_=0,
                )
            ),
            0,
        )
        purchased = func.coalesce(
            func.sum(
                case(
                    (Transaction.tx_type == "purchase", Transaction.amount),
                    else_=0,
                )
            ),
            0,
        )
        earned = func.coalesce(
            func.sum(
                case(
                    (Transaction.tx_type == "settlement_credit", Transaction.amount),
                    (Transaction.tx_type == "invocation_credit", Transaction.amount),
                    (Transaction.tx_type == "consolidation_in", Transaction.amount),
                    else_=0,
                )
            ),
            0,
        )
        spent = func.coalesce(
            func.sum(
                case(
                    (Transaction.tx_type == "settlement_debit", func.abs(Transaction.amount)),
                    (Transaction.tx_type == "invocation_debit", func.abs(Transaction.amount)),
                    (Transaction.tx_type == "consolidation_out", func.abs(Transaction.amount)),
                    else_=0,
                )
            ),
            0,
        )

        result = await self.db_session.execute(
            select(
                granted.label("total_granted"),
                purchased.label("total_purchased"),
                earned.label("total_earned"),
                spent.label("total_spent"),
                func.count().label("transaction_count"),
            ).where(Transaction.wallet_id == wallet_id)
        )
        row = result.one()
        return {
            "total_granted": row.total_granted,
            "total_purchased": row.total_purchased,
            "total_earned": row.total_earned,
            "total_spent": row.total_spent,
            "transaction_count": row.transaction_count,
        }
