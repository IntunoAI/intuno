
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_session
from src.workflow.models.entities import (
    ExecutionStatus,
    ProcessEntry,
    ProcessStatus,
    StepType,
    WorkflowExecution,
)

_STEP_TYPE_MAP = {
    "agent": StepType.agent,
    "skill": StepType.skill,
    "condition": StepType.condition,
    "sub_workflow": StepType.sub_workflow,
    "plan": StepType.plan,
}


class ExecutionRepository:
    def __init__(self, session: AsyncSession = Depends(get_session)) -> None:
        self._session = session

    # -- Execution CRUD --------------------------------------------------------

    async def create_execution(
        self,
        *,
        workflow_id: uuid.UUID,
        trigger_data: dict[str, Any] | None = None,
        parent_execution_id: uuid.UUID | None = None,
    ) -> WorkflowExecution:
        entity = WorkflowExecution(
            workflow_id=workflow_id,
            trigger_data=trigger_data,
            parent_execution_id=parent_execution_id,
        )
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def get_execution(self, execution_id: uuid.UUID) -> WorkflowExecution | None:
        return await self._session.get(WorkflowExecution, execution_id)

    async def update_execution(
        self, execution_id: uuid.UUID, **fields: Any
    ) -> None:
        stmt = (
            update(WorkflowExecution)
            .where(WorkflowExecution.id == execution_id)
            .values(**fields)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_executions(
        self,
        workflow_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowExecution]:
        stmt = select(WorkflowExecution).order_by(WorkflowExecution.started_at.desc())
        if workflow_id is not None:
            stmt = stmt.where(WorkflowExecution.workflow_id == workflow_id)
        if status is not None:
            stmt = stmt.where(WorkflowExecution.status == ExecutionStatus(status))
        stmt = stmt.limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_execution_running(self, execution_id: uuid.UUID) -> None:
        await self.update_execution(execution_id, status=ExecutionStatus.running)

    async def mark_execution_completed(self, execution_id: uuid.UUID) -> None:
        await self.update_execution(
            execution_id,
            status=ExecutionStatus.completed,
            completed_at=datetime.now(timezone.utc),
        )

    async def mark_execution_failed(
        self, execution_id: uuid.UUID, error: str
    ) -> None:
        await self.update_execution(
            execution_id,
            status=ExecutionStatus.failed,
            completed_at=datetime.now(timezone.utc),
            error=error,
        )

    # -- Process Entry CRUD ----------------------------------------------------

    async def create_process_entry(
        self,
        *,
        execution_id: uuid.UUID,
        step_id: str,
        step_type: str,
        target_name: str,
    ) -> ProcessEntry:
        entity = ProcessEntry(
            execution_id=execution_id,
            step_id=step_id,
            type=_STEP_TYPE_MAP.get(step_type, StepType.agent),
            target_name=target_name,
        )
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update_process_entry(
        self, entry_id: uuid.UUID, **fields: Any
    ) -> None:
        stmt = (
            update(ProcessEntry)
            .where(ProcessEntry.id == entry_id)
            .values(**fields)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def list_process_entries(
        self, execution_id: uuid.UUID
    ) -> list[ProcessEntry]:
        stmt = (
            select(ProcessEntry)
            .where(ProcessEntry.execution_id == execution_id)
            .order_by(ProcessEntry.started_at.asc().nulls_last())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def mark_process_running(self, entry_id: uuid.UUID) -> None:
        await self.update_process_entry(
            entry_id,
            status=ProcessStatus.running,
            started_at=datetime.now(timezone.utc),
        )

    async def mark_process_completed(
        self,
        entry_id: uuid.UUID,
        output: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        tokens_used: int | None = None,
        cost: float | None = None,
        attempt: int | None = None,
    ) -> None:
        fields: dict[str, Any] = {
            "status": ProcessStatus.completed,
            "completed_at": datetime.now(timezone.utc),
            "output": output,
            "duration_ms": duration_ms,
            "tokens_used": tokens_used,
            "cost": cost,
        }
        if attempt is not None:
            fields["attempt"] = attempt
        await self.update_process_entry(entry_id, **fields)

    async def mark_process_failed(
        self, entry_id: uuid.UUID, error: str, attempt: int | None = None
    ) -> None:
        fields: dict[str, Any] = {
            "status": ProcessStatus.failed,
            "completed_at": datetime.now(timezone.utc),
            "error": error,
        }
        if attempt is not None:
            fields["attempt"] = attempt
        await self.update_process_entry(entry_id, **fields)

    async def mark_process_skipped(self, entry_id: uuid.UUID) -> None:
        await self.update_process_entry(entry_id, status=ProcessStatus.skipped)

    async def mark_in_flight_entries_timed_out(
        self, execution_id: uuid.UUID, error: str
    ) -> None:
        """Fail all pending/running process entries for an execution (used on timeout)."""
        stmt = (
            update(ProcessEntry)
            .where(
                ProcessEntry.execution_id == execution_id,
                ProcessEntry.status.in_([ProcessStatus.pending, ProcessStatus.running]),
            )
            .values(
                status=ProcessStatus.failed,
                completed_at=datetime.now(timezone.utc),
                error=error,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def mark_execution_cancelled(self, execution_id: uuid.UUID) -> None:
        await self.update_execution(
            execution_id,
            status=ExecutionStatus.cancelled,
            completed_at=datetime.now(timezone.utc),
            error="Execution cancelled",
        )
