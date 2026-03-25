"""Core orchestration engine — walks the workflow DAG, executes steps,
manages the context bus and process table."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import Depends

from src.core.settings import settings
from src.workflow.exceptions import StepExecutionError
from src.workflow.models.dsl import RecoveryConfig, WorkflowDef, WorkflowStep
from src.workflow.repositories.executions import ExecutionRepository
from src.workflow.utils.concurrency import ConcurrencyLimiter
from src.workflow.utils.context_bus import ContextBus
from src.workflow.utils.dsl_parser import build_dependency_graph, topological_order
from src.workflow.utils.recovery import RecoveryManager
from src.workflow.utils.resolver import Resolver
from src.workflow.utils.template import TemplateContext, TemplateEngine

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        exec_repo: ExecutionRepository = Depends(),
        context_bus: ContextBus = Depends(),
        resolver: Resolver = Depends(),
        recovery: RecoveryManager = Depends(),
        concurrency_limiter: ConcurrencyLimiter = Depends(),
    ) -> None:
        self._exec_repo = exec_repo
        self._ctx = context_bus
        self._resolver = resolver
        self._recovery = recovery
        self._limiter = concurrency_limiter

    async def run(
        self,
        execution_id: uuid.UUID,
        context_id: uuid.UUID,
        trigger_data: dict[str, Any],
        workflow_def: WorkflowDef,
        workflow_id: uuid.UUID | None = None,
    ) -> None:
        """Execute a full workflow.  Updates execution + process entries in place."""
        wf_sem = None
        if workflow_id is not None:
            wf_sem = self._limiter.workflow_semaphore(
                workflow_id, workflow_def.max_concurrent_executions,
            )
            await wf_sem.acquire()

        await self._exec_repo.mark_execution_running(execution_id)

        step_map = {s.id: s for s in workflow_def.steps}
        deps = build_dependency_graph(workflow_def)
        tiers = topological_order(deps)

        step_outputs: dict[str, Any] = {}
        skipped: set[str] = set()

        entry_ids: dict[str, uuid.UUID] = {}
        for step in workflow_def.steps:
            entry = await self._exec_repo.create_process_entry(
                execution_id=execution_id,
                step_id=step.id,
                step_type=step.resolved_type,
                target_name=step.target_ref or step.id,
            )
            entry_ids[step.id] = entry.id

        max_duration = (
            workflow_def.max_duration_seconds
            if workflow_def.max_duration_seconds is not None
            else settings.WORKFLOW_DEFAULT_MAX_DURATION_SECONDS
        )

        try:
            if max_duration and max_duration > 0:
                await asyncio.wait_for(
                    self._run_tiers(
                        tiers, step_map, entry_ids, context_id,
                        trigger_data, step_outputs, workflow_def, skipped,
                        execution_id,
                    ),
                    timeout=max_duration,
                )
            else:
                await self._run_tiers(
                    tiers, step_map, entry_ids, context_id,
                    trigger_data, step_outputs, workflow_def, skipped,
                    execution_id,
                )

            await self._exec_repo.mark_execution_completed(execution_id)
        except asyncio.TimeoutError:
            msg = f"Workflow exceeded max duration of {max_duration}s"
            logger.error(msg)
            await self._exec_repo.mark_in_flight_entries_timed_out(
                execution_id, msg,
            )
            await self._exec_repo.mark_execution_failed(execution_id, msg)
            raise StepExecutionError(msg)
        except (StepExecutionError, Exception) as exc:
            await self._exec_repo.mark_execution_failed(execution_id, str(exc))
            raise
        finally:
            if wf_sem is not None:
                await wf_sem.release()
            await self._ctx.finalize(context_id)

    async def _run_tiers(
        self,
        tiers: list[list[str]],
        step_map: dict[str, WorkflowStep],
        entry_ids: dict[str, uuid.UUID],
        context_id: uuid.UUID,
        trigger_data: dict[str, Any],
        step_outputs: dict[str, Any],
        workflow_def: WorkflowDef,
        skipped: set[str],
        execution_id: uuid.UUID,
    ) -> None:
        """Walk tiers sequentially; within each tier, run steps in parallel."""
        for tier in tiers:
            runnable = [sid for sid in tier if sid not in skipped]
            if not runnable:
                continue

            if len(runnable) == 1:
                await self._execute_step(
                    step_map[runnable[0]],
                    entry_ids[runnable[0]],
                    context_id,
                    trigger_data,
                    step_outputs,
                    workflow_def.recovery,
                    step_map,
                    skipped,
                    execution_id,
                    workflow_def,
                )
            else:
                async with asyncio.TaskGroup() as tg:
                    for sid in runnable:
                        tg.create_task(
                            self._execute_step(
                                step_map[sid],
                                entry_ids[sid],
                                context_id,
                                trigger_data,
                                step_outputs,
                                workflow_def.recovery,
                                step_map,
                                skipped,
                                execution_id,
                                workflow_def,
                            )
                        )

    async def _execute_step(
        self,
        step: WorkflowStep,
        entry_id: uuid.UUID,
        context_id: uuid.UUID,
        trigger_data: dict[str, Any],
        step_outputs: dict[str, Any],
        default_recovery: RecoveryConfig,
        step_map: dict[str, WorkflowStep],
        skipped: set[str],
        execution_id: uuid.UUID,
        workflow_def: WorkflowDef,
    ) -> None:
        if step.id in skipped:
            await self._exec_repo.mark_process_skipped(entry_id)
            return

        await self._exec_repo.mark_process_running(entry_id)
        t0 = time.monotonic()

        ctx_snapshot = await self._ctx.snapshot(context_id)
        engine = TemplateEngine(
            TemplateContext(trigger=trigger_data, steps=step_outputs, context=ctx_snapshot)
        )

        if step.resolved_type == "condition":
            await self._handle_condition(
                step, entry_id, engine, step_outputs, skipped
            )
            return

        if step.resolved_type == "sub_workflow":
            await self._handle_sub_workflow(
                step, entry_id, context_id, engine,
                step_outputs, execution_id, t0,
            )
            return

        if step.resolved_type == "plan":
            await self._handle_plan(
                step, entry_id, context_id, trigger_data,
                engine, step_outputs, skipped, execution_id,
                workflow_def, t0,
            )
            return

        ref = step.target_ref
        if not ref:
            raise StepExecutionError(f"Step '{step.id}' has no agent or skill reference")

        resolved_input = engine.render(step.input or {})
        target = await self._resolver.resolve(ref)

        await self._exec_repo.update_process_entry(
            entry_id, target_id=target.agent_id, target_name=target.name
        )

        recovery_cfg = step.recovery or default_recovery

        try:
            recovery_result = await self._recovery.execute_with_recovery(
                target, resolved_input, recovery_cfg, original_ref=ref,
                agent_concurrency_limit=workflow_def.max_concurrent_per_agent,
            )
        except StepExecutionError as exc:
            await self._exec_repo.mark_process_failed(
                entry_id, str(exc), attempt=exc.attempt
            )
            raise

        if recovery_result.fallback_used:
            await self._exec_repo.update_process_entry(
                entry_id,
                target_id=recovery_result.final_target.agent_id,
                target_name=recovery_result.final_target.name,
            )

        duration_ms = int((time.monotonic() - t0) * 1000)
        output_data = recovery_result.data.get("data")

        step_outputs[step.id] = {"output": output_data}
        await self._ctx.write(context_id, step.id, output_data)

        await self._exec_repo.mark_process_completed(
            entry_id,
            output=output_data,
            duration_ms=duration_ms,
            tokens_used=None,
            cost=None,
            attempt=recovery_result.attempts_total,
        )

    async def _handle_condition(
        self,
        step: WorkflowStep,
        entry_id: uuid.UUID,
        engine: TemplateEngine,
        step_outputs: dict[str, Any],
        skipped: set[str],
    ) -> None:
        """Evaluate condition branches, mark non-taken goto targets as skipped."""
        chosen_goto: str | None = None

        if step.when:
            for branch in step.when:
                if branch.else_flag:
                    chosen_goto = branch.goto
                    break
                if branch.if_expr and engine.evaluate(branch.if_expr):
                    chosen_goto = branch.goto
                    break

        all_gotos = {b.goto for b in (step.when or [])}
        for goto_id in all_gotos:
            if goto_id != chosen_goto:
                skipped.add(goto_id)

        output = {"chosen": chosen_goto}
        step_outputs[step.id] = {"output": output}

        await self._exec_repo.mark_process_completed(entry_id, output=output, duration_ms=0)

    # -- Sub-workflow handling --------------------------------------------------

    async def _handle_sub_workflow(
        self,
        step: WorkflowStep,
        entry_id: uuid.UUID,
        parent_context_id: uuid.UUID,
        engine: TemplateEngine,
        step_outputs: dict[str, Any],
        parent_execution_id: uuid.UUID,
        t0: float,
    ) -> None:
        """Execute a child workflow inline and capture its output."""
        from src.workflow.repositories.workflows import WorkflowRepository

        if not step.workflow:
            raise StepExecutionError(
                f"Sub-workflow step '{step.id}' has no workflow reference"
            )

        wf_ref = engine.render(step.workflow) if isinstance(step.workflow, str) else step.workflow

        wf_repo = WorkflowRepository(self._exec_repo._session)
        child_wf = await wf_repo.get_latest_version(wf_ref)
        if child_wf is None:
            try:
                wf_id = uuid.UUID(wf_ref)
                child_wf = await wf_repo.get_by_id(wf_id)
            except ValueError:
                pass
        if child_wf is None:
            raise StepExecutionError(
                f"Sub-workflow '{wf_ref}' not found (step '{step.id}')"
            )

        child_def = WorkflowDef.model_validate(child_wf.definition)
        child_trigger = engine.render(step.input or {})

        child_exec = await self._exec_repo.create_execution(
            workflow_id=child_wf.id,
            trigger_data=child_trigger,
            parent_execution_id=parent_execution_id,
        )

        parent_snapshot = await self._ctx.snapshot(parent_context_id)
        await self._ctx.write(child_exec.context_id, "__parent_context", parent_snapshot)

        await self.run(
            execution_id=child_exec.id,
            context_id=child_exec.context_id,
            trigger_data=child_trigger,
            workflow_def=child_def,
            workflow_id=child_wf.id,
        )

        child_snapshot = await self._ctx.snapshot(child_exec.context_id)
        output_data = {
            k: v for k, v in child_snapshot.items() if k != "__parent_context"
        }

        duration_ms = int((time.monotonic() - t0) * 1000)
        step_outputs[step.id] = {"output": output_data}
        await self._ctx.write(parent_context_id, step.id, output_data)

        await self._exec_repo.mark_process_completed(
            entry_id, output=output_data, duration_ms=duration_ms,
        )

    # -- Dynamic step generation (plan) ----------------------------------------

    async def _handle_plan(
        self,
        step: WorkflowStep,
        entry_id: uuid.UUID,
        context_id: uuid.UUID,
        trigger_data: dict[str, Any],
        engine: TemplateEngine,
        step_outputs: dict[str, Any],
        skipped: set[str],
        execution_id: uuid.UUID,
        workflow_def: WorkflowDef,
        t0: float,
    ) -> None:
        """Use an LLM planner to generate steps, inject them into the DAG, and run them."""
        from src.workflow.utils.planner import Planner

        if not step.goal:
            raise StepExecutionError(f"Plan step '{step.id}' has no goal")

        rendered_goal = engine.render(step.goal)
        if not isinstance(rendered_goal, str):
            rendered_goal = str(rendered_goal)

        ctx_snapshot = await self._ctx.snapshot(context_id)
        planner = Planner()

        try:
            generated_steps = await planner.generate_steps(
                goal=rendered_goal,
                context={"trigger": trigger_data, "steps": step_outputs, "context": ctx_snapshot},
            )
        except StepExecutionError as exc:
            await self._exec_repo.mark_process_failed(entry_id, str(exc))
            raise

        plan_output = {
            "goal": rendered_goal,
            "generated_step_ids": [s.id for s in generated_steps],
        }
        plan_duration = int((time.monotonic() - t0) * 1000)
        step_outputs[step.id] = {"output": plan_output}
        await self._ctx.write(context_id, step.id, plan_output)
        await self._exec_repo.mark_process_completed(
            entry_id, output=plan_output, duration_ms=plan_duration,
        )

        gen_step_map: dict[str, WorkflowStep] = {}
        gen_entry_ids: dict[str, uuid.UUID] = {}
        for gs in generated_steps:
            gen_step_map[gs.id] = gs
            entry = await self._exec_repo.create_process_entry(
                execution_id=execution_id,
                step_id=gs.id,
                step_type=gs.resolved_type,
                target_name=gs.target_ref or gs.id,
            )
            gen_entry_ids[gs.id] = entry.id

        gen_wf = WorkflowDef(
            name=f"{workflow_def.name}::{step.id}::dynamic",
            steps=generated_steps,
            recovery=workflow_def.recovery,
            max_duration_seconds=workflow_def.max_duration_seconds,
            max_concurrent_per_agent=workflow_def.max_concurrent_per_agent,
        )
        gen_deps = build_dependency_graph(gen_wf)
        gen_tiers = topological_order(gen_deps)

        gen_skipped: set[str] = set()
        for tier in gen_tiers:
            runnable = [sid for sid in tier if sid not in gen_skipped]
            if not runnable:
                continue
            if len(runnable) == 1:
                await self._execute_step(
                    gen_step_map[runnable[0]],
                    gen_entry_ids[runnable[0]],
                    context_id,
                    trigger_data,
                    step_outputs,
                    workflow_def.recovery,
                    gen_step_map,
                    gen_skipped,
                    execution_id,
                    workflow_def,
                )
            else:
                async with asyncio.TaskGroup() as tg:
                    for sid in runnable:
                        tg.create_task(
                            self._execute_step(
                                gen_step_map[sid],
                                gen_entry_ids[sid],
                                context_id,
                                trigger_data,
                                step_outputs,
                                workflow_def.recovery,
                                gen_step_map,
                                gen_skipped,
                                execution_id,
                                workflow_def,
                            )
                        )
