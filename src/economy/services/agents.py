"""Economy agent service — creates simulated agents for the marketplace.

After merge, this service uses wisdom's Agent model directly. The
``capabilities`` field from the economy schema is mapped to ``tags``
on wisdom's Agent model.
"""

import uuid

from fastapi import Depends, HTTPException

from src.core.settings import settings
from src.models.registry import Agent
from src.economy.models.wallet import Transaction, Wallet
from src.economy.repositories.agents import AgentRepository
from src.economy.repositories.wallets import WalletRepository
from src.economy.schemas.agent import (
    AgentCreate,
    AgentListResponse,
    AgentResponse,
    AgentUpdate,
)


class AgentService:
    """Business logic for agent registration, lookup, and lifecycle."""

    def __init__(
        self,
        agent_repository: AgentRepository = Depends(),
        wallet_repository: WalletRepository = Depends(),
    ):
        self.agent_repository = agent_repository
        self.wallet_repository = wallet_repository

    async def create_agent(self, payload: AgentCreate) -> AgentResponse:
        """Register a new agent, provision its wallet, and issue welcome grant."""
        agent_id_str = payload.name.lower().replace(" ", "-") + "-" + uuid.uuid4().hex[:8]
        agent = Agent(
            agent_id=agent_id_str,
            name=payload.name,
            description=payload.description,
            # Map economy 'capabilities' to wisdom's 'tags'
            tags=payload.capabilities or payload.tags or [],
            category=payload.category,
            input_schema=payload.input_schema,
            pricing_strategy=payload.pricing_strategy,
            base_price=float(payload.base_price) if payload.base_price else None,
            # Required wisdom fields with simulator defaults
            invoke_endpoint="https://simulator.internal/noop",
            auth_type="public",
            version="1.0.0",
            trust_verification="self-signed",
            # Simulated agents need a placeholder user_id
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        )
        agent = await self.agent_repository.create(agent)

        wallet = Wallet(agent_id=agent.id, wallet_type="agent", balance=0)
        wallet = await self.wallet_repository.create(wallet)

        total_grant = 0

        welcome = settings.ECONOMY_WELCOME_BONUS_CREDITS
        if welcome > 0:
            total_grant += welcome
            await self.wallet_repository.create_transaction(
                Transaction(
                    wallet_id=wallet.id,
                    amount=welcome,
                    tx_type="grant_welcome",
                    description="Welcome bonus",
                )
            )

        extra = payload.initial_balance - welcome
        if extra > 0:
            total_grant += extra
            await self.wallet_repository.create_transaction(
                Transaction(
                    wallet_id=wallet.id,
                    amount=extra,
                    tx_type="grant_promotional",
                    description="Initial balance top-up",
                )
            )

        if total_grant > 0:
            await self.wallet_repository.update_balance(wallet.id, total_grant)

        await self.agent_repository.db_session.refresh(agent)
        return AgentResponse.model_validate(agent)

    async def get_agent(self, agent_id: uuid.UUID) -> AgentResponse:
        """Fetch a single agent or raise 404."""
        agent = await self.agent_repository.get_by_id(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return AgentResponse.model_validate(agent)

    async def list_agents(
        self,
        is_active: bool | None = None,
        capability: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentListResponse]:
        """Return a filtered, paginated list of agents."""
        agents = await self.agent_repository.list_all(
            is_active=is_active,
            capability=capability,
            limit=limit,
            offset=offset,
        )
        return [AgentListResponse.model_validate(a) for a in agents]

    async def update_agent(
        self,
        agent_id: uuid.UUID,
        payload: AgentUpdate,
    ) -> AgentResponse:
        """Apply a partial update to an existing agent."""
        values = payload.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=400, detail="No fields to update")
        agent = await self.agent_repository.update(agent_id, values)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return AgentResponse.model_validate(agent)

    async def delete_agent(self, agent_id: uuid.UUID) -> None:
        """Delete an agent and its wallet."""
        deleted = await self.agent_repository.delete(agent_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Agent not found")
