"""Orchestrator utility: plan then execute (sequential); task timeout; step progress."""

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID

from src.utilities.executor import Executor, ExecutorContext, StepResult
from src.utilities.planner import StepSpec, get_plan


@dataclass
class OrchestratorContext:
    """Context for running the orchestrator: user, integration, timeout, fallback, progress callback."""

    user_id: UUID
    integration_id: Optional[UUID]
    conversation_id: Optional[UUID]
    message_id: Optional[UUID]
    task_timeout_seconds: int
    external_user_id: Optional[str] = None
    fallback_agent_id: Optional[str] = None
    fallback_capability_id: Optional[str] = None
    on_step_progress: Optional[Callable] = None


@dataclass
class OrchestratorResult:
    """Result of running the orchestrator: success, result/error, and steps list."""

    success: bool
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)


def _step_to_dict(
    step_spec: StepSpec,
    status: str,
    result: Optional[StepResult] = None,
) -> Dict[str, Any]:
    """Build step payload for task.steps (step_id, status, result?, error?)."""
    out: Dict[str, Any] = {
        "step_id": str(step_spec.id),
        "status": status,
    }
    if result is not None:
        out["result"] = result.data
        out["error"] = result.error
    return out


class Orchestrator:
    """
    Coordinates plan + execute: calls Planner then runs each step via Executor.
    Enforces task-level timeout; reports step progress via callback.
    """

    def __init__(self, executor: Executor):
        self.executor = executor

    @staticmethod
    async def _notify_progress(
        callback: Optional[Callable],
        steps: List[Dict[str, Any]],
    ) -> None:
        if callback is None:
            return
        result = callback(steps)
        if inspect.isawaitable(result):
            await result

    async def run(
        self,
        goal: str,
        input_data: Dict[str, Any],
        context: OrchestratorContext,
    ) -> OrchestratorResult:
        """
        Plan from goal + input, then execute steps sequentially.
        Empty plan -> failure. Task timeout -> stop and mark timeout.
        :param goal: str
        :param input_data: dict
        :param context: OrchestratorContext
        :return: OrchestratorResult
        """
        steps_specs = await get_plan(goal, input_data or {})
        if not steps_specs:
            return OrchestratorResult(
                success=False,
                error_message="Empty plan: no steps to run.",
                steps=[],
            )

        start_time = time.time()
        steps_out: List[Dict[str, Any]] = []
        last_result: Optional[Dict[str, Any]] = None

        executor_ctx = ExecutorContext(
            user_id=context.user_id,
            integration_id=context.integration_id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            external_user_id=context.external_user_id,
            fallback_agent_id=context.fallback_agent_id,
            fallback_capability_id=context.fallback_capability_id,
        )

        for step_spec in steps_specs:
            if (time.time() - start_time) >= context.task_timeout_seconds:
                steps_out.append(
                    _step_to_dict(step_spec, "pending")
                )
                await self._notify_progress(context.on_step_progress, steps_out)
                return OrchestratorResult(
                    success=False,
                    error_message="Task timeout exceeded.",
                    steps=steps_out,
                )

            steps_out.append(_step_to_dict(step_spec, "running"))
            await self._notify_progress(context.on_step_progress, steps_out)

            # Pass previous step result into this step's input so later steps can use earlier outputs
            if last_result is not None:
                step_spec.input = {**step_spec.input, "result_from_previous_step": last_result}

            step_result = await self.executor.execute_step(step_spec, executor_ctx)

            if step_result.conversation_id and not executor_ctx.conversation_id:
                executor_ctx.conversation_id = step_result.conversation_id

            if step_result.success:
                steps_out[-1] = _step_to_dict(step_spec, "completed", step_result)
                last_result = step_result.data
            else:
                steps_out[-1] = _step_to_dict(step_spec, "failed", step_result)
                await self._notify_progress(context.on_step_progress, steps_out)
                return OrchestratorResult(
                    success=False,
                    error_message=step_result.error or "Step failed.",
                    steps=steps_out,
                )
            await self._notify_progress(context.on_step_progress, steps_out)

        return OrchestratorResult(
            success=True,
            result=last_result,
            steps=steps_out,
        )
