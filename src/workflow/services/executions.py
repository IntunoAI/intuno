from __future__ import annotations

import uuid

from fastapi import Depends

from src.database import get_background_runner
from src.workflow.exceptions import NotFoundException
from src.workflow.models.dsl import WorkflowDef
from src.workflow.models.schemas import (
    ContextSnapshotResponse,
    ExecutionResponse,
    ProcessEntryResponse,
    TriggerRequest,
)
from src.workflow.repositories.executions import ExecutionRepository
from src.workflow.repositories.workflows import WorkflowRepository
from src.workflow.utils.background import BackgroundRunner
from src.workflow.utils.context_bus import ContextBus


class ExecutionService:
    def __init__(
        self,
        wf_repo: WorkflowRepository = Depends(),
        exec_repo: ExecutionRepository = Depends(),
        context_bus: ContextBus = Depends(),
        background_runner: BackgroundRunner = Depends(get_background_runner),
    ) -> None:
        self._wf_repo = wf_repo
        self._exec_repo = exec_repo
        self._ctx = context_bus
        self._runner = background_runner

    async def trigger(
        self, workflow_id: uuid.UUID, request: TriggerRequest
    ) -> ExecutionResponse:
        wf = await self._wf_repo.get_by_id(workflow_id)
        if wf is None:
            raise NotFoundException(f"Workflow '{workflow_id}' not found")

        workflow_def = WorkflowDef.model_validate(wf.definition)

        execution = await self._exec_repo.create_execution(
            workflow_id=wf.id,
            trigger_data=request.trigger_data,
        )

        self._runner.submit(
            execution_id=execution.id,
            context_id=execution.context_id,
            trigger_data=execution.trigger_data or {},
            workflow_def=workflow_def,
            workflow_id=wf.id,
        )

        return ExecutionResponse.model_validate(execution)

    async def cancel(self, execution_id: uuid.UUID) -> ExecutionResponse:
        execution = await self._exec_repo.get_execution(execution_id)
        if execution is None:
            raise NotFoundException(f"Execution '{execution_id}' not found")

        cancelled = await self._runner.cancel(execution_id)
        if not cancelled:
            await self._exec_repo.mark_execution_cancelled(execution_id)

        refreshed = await self._exec_repo.get_execution(execution_id)
        return ExecutionResponse.model_validate(refreshed)

    async def get_status(self, execution_id: uuid.UUID) -> ExecutionResponse | None:
        entity = await self._exec_repo.get_execution(execution_id)
        if entity is None:
            return None
        return ExecutionResponse.model_validate(entity)

    async def get_process_table(
        self, execution_id: uuid.UUID
    ) -> list[ProcessEntryResponse]:
        entries = await self._exec_repo.list_process_entries(execution_id)
        return [ProcessEntryResponse.model_validate(e) for e in entries]

    async def get_context(
        self, execution_id: uuid.UUID
    ) -> ContextSnapshotResponse | None:
        execution = await self._exec_repo.get_execution(execution_id)
        if execution is None:
            return None
        data = await self._ctx.snapshot(execution.context_id)
        return ContextSnapshotResponse(
            context_id=execution.context_id, entries=data
        )

    async def list_executions(
        self,
        workflow_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ExecutionResponse]:
        entities = await self._exec_repo.list_executions(
            workflow_id=workflow_id, status=status, limit=limit, offset=offset
        )
        return [ExecutionResponse.model_validate(e) for e in entities]
