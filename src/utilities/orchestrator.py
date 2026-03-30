"""Orchestrator utility: plan then execute with parallel DAG support.

Steps with no dependencies (or whose dependencies are already completed)
run concurrently via asyncio.gather(). Steps with depends_on wait for
their dependencies to finish first.

Backward-compatible: plans without depends_on execute sequentially
(each step implicitly depends on the previous one).
"""

import asyncio
import inspect
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set
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


def _has_dag_dependencies(steps: List[StepSpec]) -> bool:
    """Return True if any step has explicit depends_on set."""
    return any(step.depends_on for step in steps)


def _topological_levels(steps: List[StepSpec]) -> List[List[StepSpec]]:
    """Group steps into execution levels via topological sort.

    Level 0: steps with no dependencies
    Level N: steps whose dependencies are all in levels < N
    """
    step_by_id = {s.id: s for s in steps}
    in_degree: Dict[UUID, int] = {s.id: len(s.depends_on) for s in steps}
    dependents: Dict[UUID, List[UUID]] = defaultdict(list)
    for s in steps:
        for dep_id in s.depends_on:
            dependents[dep_id].append(s.id)

    levels: List[List[StepSpec]] = []
    ready = [s.id for s in steps if in_degree[s.id] == 0]

    while ready:
        level = [step_by_id[sid] for sid in ready]
        levels.append(level)
        next_ready = []
        for sid in ready:
            for dependent_id in dependents[sid]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    next_ready.append(dependent_id)
        ready = next_ready

    return levels


class Orchestrator:
    """
    Coordinates plan + execute: calls Planner then runs steps via Executor.
    Supports parallel execution when steps declare depends_on.
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
        """Plan from goal + input, then execute steps (parallel when possible)."""
        steps_specs = await get_plan(goal, input_data or {})
        if not steps_specs:
            return OrchestratorResult(
                success=False,
                error_message="Empty plan: no steps to run.",
                steps=[],
            )

        if _has_dag_dependencies(steps_specs):
            return await self._run_parallel(steps_specs, input_data, context)
        return await self._run_sequential(steps_specs, input_data, context)

    async def _run_sequential(
        self,
        steps_specs: List[StepSpec],
        input_data: Dict[str, Any],
        context: OrchestratorContext,
    ) -> OrchestratorResult:
        """Original sequential execution — backward compatible."""
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
        )

        for step_spec in steps_specs:
            if (time.time() - start_time) >= context.task_timeout_seconds:
                steps_out.append(_step_to_dict(step_spec, "pending"))
                await self._notify_progress(context.on_step_progress, steps_out)
                return OrchestratorResult(
                    success=False,
                    error_message="Task timeout exceeded.",
                    steps=steps_out,
                )

            steps_out.append(_step_to_dict(step_spec, "running"))
            await self._notify_progress(context.on_step_progress, steps_out)

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

    async def _run_parallel(
        self,
        steps_specs: List[StepSpec],
        input_data: Dict[str, Any],
        context: OrchestratorContext,
    ) -> OrchestratorResult:
        """DAG-based parallel execution — steps in the same level run concurrently."""
        start_time = time.time()
        levels = _topological_levels(steps_specs)

        # Track results by step ID
        step_results: Dict[UUID, StepResult] = {}
        steps_out_map: Dict[UUID, Dict[str, Any]] = {}
        step_by_id = {s.id: s for s in steps_specs}

        executor_ctx = ExecutorContext(
            user_id=context.user_id,
            integration_id=context.integration_id,
            conversation_id=context.conversation_id,
            message_id=context.message_id,
            external_user_id=context.external_user_id,
            fallback_agent_id=context.fallback_agent_id,
        )

        for level in levels:
            if (time.time() - start_time) >= context.task_timeout_seconds:
                for step in level:
                    steps_out_map[step.id] = _step_to_dict(step, "pending")
                steps_out = [steps_out_map.get(s.id, _step_to_dict(s, "pending")) for s in steps_specs]
                await self._notify_progress(context.on_step_progress, steps_out)
                return OrchestratorResult(
                    success=False,
                    error_message="Task timeout exceeded.",
                    steps=steps_out,
                )

            # Mark all steps in this level as running
            for step in level:
                steps_out_map[step.id] = _step_to_dict(step, "running")
            steps_out = [steps_out_map.get(s.id, _step_to_dict(s, "pending")) for s in steps_specs]
            await self._notify_progress(context.on_step_progress, steps_out)

            # Inject dependency results into step inputs
            for step in level:
                dep_results = {}
                for dep_id in step.depends_on:
                    if dep_id in step_results and step_results[dep_id].data:
                        dep_results[str(dep_id)] = step_results[dep_id].data
                if dep_results:
                    step.input = {**step.input, "dependency_results": dep_results}

            # Execute all steps in this level concurrently
            async def _run_step(step: StepSpec) -> tuple[StepSpec, StepResult]:
                result = await self.executor.execute_step(step, executor_ctx)
                return step, result

            results = await asyncio.gather(
                *[_run_step(step) for step in level],
                return_exceptions=True,
            )

            # Process results
            failed = False
            error_msg = None
            for res in results:
                if isinstance(res, Exception):
                    # Shouldn't happen but handle gracefully
                    failed = True
                    error_msg = str(res)
                    continue
                step, step_result = res
                step_results[step.id] = step_result

                if step_result.conversation_id and not executor_ctx.conversation_id:
                    executor_ctx.conversation_id = step_result.conversation_id

                if step_result.success:
                    steps_out_map[step.id] = _step_to_dict(step, "completed", step_result)
                else:
                    steps_out_map[step.id] = _step_to_dict(step, "failed", step_result)
                    failed = True
                    error_msg = step_result.error or "Step failed."

            steps_out = [steps_out_map.get(s.id, _step_to_dict(s, "pending")) for s in steps_specs]
            await self._notify_progress(context.on_step_progress, steps_out)

            if failed:
                return OrchestratorResult(
                    success=False,
                    error_message=error_msg,
                    steps=steps_out,
                )

        # Success: return the result from the last level's last step
        steps_out = [steps_out_map.get(s.id, _step_to_dict(s, "pending")) for s in steps_specs]
        last_step = steps_specs[-1]
        last_data = step_results.get(last_step.id)
        return OrchestratorResult(
            success=True,
            result=last_data.data if last_data else None,
            steps=steps_out,
        )
