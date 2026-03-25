from __future__ import annotations

import uuid
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.workflow.models.entities import WorkflowDefinition


class WorkflowRepository:
    def __init__(self, session: AsyncSession = Depends(get_session)) -> None:
        self._session = session

    async def create(
        self,
        *,
        name: str,
        version: int,
        owner_id: uuid.UUID | None,
        definition: dict[str, Any],
        triggers: list[dict[str, Any]] | None,
        recovery: dict[str, Any] | None,
    ) -> WorkflowDefinition:
        entity = WorkflowDefinition(
            name=name,
            version=version,
            owner_id=owner_id,
            definition=definition,
            triggers=triggers,
            recovery=recovery,
        )
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_by_id(self, workflow_id: uuid.UUID) -> WorkflowDefinition | None:
        return await self._session.get(WorkflowDefinition, workflow_id)

    async def list(
        self,
        name: str | None = None,
        owner_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowDefinition]:
        stmt = select(WorkflowDefinition).order_by(WorkflowDefinition.created_at.desc())
        if name is not None:
            stmt = stmt.where(WorkflowDefinition.name == name)
        if owner_id is not None:
            stmt = stmt.where(WorkflowDefinition.owner_id == owner_id)
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_version(self, name: str) -> WorkflowDefinition | None:
        stmt = (
            select(WorkflowDefinition)
            .where(WorkflowDefinition.name == name)
            .order_by(WorkflowDefinition.version.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
