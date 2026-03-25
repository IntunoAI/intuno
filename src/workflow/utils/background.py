"""Background runner — manages asyncio.Tasks for workflow executions.

Allows ``ExecutionService.trigger()`` to return immediately while the
workflow runs asynchronously.  Supports cancellation and graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from src.workflow.models.dsl import WorkflowDef
from src.workflow.models.entities import ExecutionStatus

logger = logging.getLogger(__name__)


class BackgroundRunner:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._tasks: dict[uuid.UUID, asyncio.Task[None]] = {}

    def submit(
        self,
        execution_id: uuid.UUID,
        context_id: uuid.UUID,
        trigger_data: dict[str, Any],
        workflow_def: WorkflowDef,
        workflow_id: uuid.UUID | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._run(execution_id, context_id, trigger_data, workflow_def, workflow_id),
            name=f"exec-{execution_id}",
        )
        self._tasks[execution_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(execution_id, None))

    async def cancel(self, execution_id: uuid.UUID) -> bool:
        task = self._tasks.get(execution_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def is_running(self, execution_id: uuid.UUID) -> bool:
        task = self._tasks.get(execution_id)
        return task is not None and not task.done()

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()

    async def _run(
        self,
        execution_id: uuid.UUID,
        context_id: uuid.UUID,
        trigger_data: dict[str, Any],
        workflow_def: WorkflowDef,
        workflow_id: uuid.UUID | None = None,
    ) -> None:
        from src.database import async_session_factory
        from src.workflow.repositories.executions import ExecutionRepository
        from src.workflow.utils.circuit_breaker import CircuitBreaker
        from src.workflow.utils.concurrency import ConcurrencyLimiter
        from src.workflow.utils.context_bus import ContextBus
        from src.workflow.utils.orchestrator import Orchestrator
        from src.workflow.utils.recovery import RecoveryManager
        from src.workflow.utils.resolver import Resolver

        async with async_session_factory() as session:
            try:
                exec_repo = ExecutionRepository(session)
                cb = CircuitBreaker(self._redis)
                resolver = Resolver(circuit_breaker=cb)
                ctx_bus = ContextBus(self._redis)
                limiter = ConcurrencyLimiter(self._redis)
                recovery = RecoveryManager(
                    resolver=resolver, circuit_breaker=cb,
                    concurrency_limiter=limiter,
                )
                orchestrator = Orchestrator(
                    exec_repo=exec_repo,
                    context_bus=ctx_bus,
                    resolver=resolver,
                    recovery=recovery,
                    concurrency_limiter=limiter,
                )

                await orchestrator.run(
                    execution_id, context_id, trigger_data, workflow_def,
                    workflow_id=workflow_id,
                )
                await session.commit()
            except asyncio.CancelledError:
                await session.rollback()
                async with async_session_factory() as cancel_session:
                    repo = ExecutionRepository(cancel_session)
                    await repo.mark_execution_cancelled(execution_id)
                    await cancel_session.commit()
                logger.info("Execution %s cancelled", execution_id)
            except Exception:
                await session.rollback()
                logger.exception("Background execution %s failed", execution_id)
