"""Pydantic models for the workflow DSL.

These represent the *definition* of a workflow as authored by the user,
parsed from YAML or JSON.  They are validated at creation time and stored
as JSON inside WorkflowDefinition.definition.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CircuitBreakerConfig(BaseModel):
    """Per-workflow circuit breaker overrides.

    Any field left as ``None`` falls back to the system-level default
    in ``Settings``.
    """

    failure_threshold: int | None = None
    window_seconds: int | None = None
    cooldown_seconds: int | None = None


class RecoveryConfig(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    backoff_base_seconds: float = Field(default=2.0, gt=0)
    semantic_fallback: bool = False
    max_alternatives: int = Field(default=2, ge=0)
    circuit_breaker: CircuitBreakerConfig | None = None


class TriggerDef(BaseModel):
    type: str = Field(
        default="event",
        description="Trigger type: 'event' (pub/sub), 'webhook', or 'cron'.",
    )
    event: str | None = Field(
        default=None,
        description="Event name for pub/sub triggers (e.g. 'complaint.received').",
    )
    cron: str | None = Field(
        default=None,
        description="Cron expression for scheduled triggers (e.g. '0 */6 * * *').",
    )


class StepConditionBranch(BaseModel):
    if_expr: str | None = Field(default=None, alias="if")
    else_flag: bool = Field(default=False, alias="else")
    goto: str


class ConvergenceConfig(BaseModel):
    """Configuration for loop convergence detection."""

    type: str = Field(
        default="max_iterations",
        description="Convergence strategy: 'similarity', 'approval', or 'max_iterations'.",
    )
    threshold: float | None = Field(
        default=None,
        description="Threshold for similarity-based convergence (0.0 to 1.0).",
    )


class LoopConfig(BaseModel):
    """Configuration for loop (feedback cycle) steps."""

    max_iterations: int = Field(default=5, ge=1, le=50)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    body: list["WorkflowStep"] = Field(
        ..., description="Steps to execute in each iteration of the loop."
    )


class AggregateConfig(BaseModel):
    """Configuration for fan-in aggregation steps."""

    sources: list[str] = Field(
        ..., description="Step IDs whose outputs to aggregate."
    )
    strategy: str = Field(
        default="merge",
        description="Aggregation strategy: 'merge', 'vote', or 'llm_summarize'.",
    )
    timeout_seconds: int | None = Field(
        default=None, description="Max wait time for all sources to complete."
    )


class WorkflowStep(BaseModel):
    id: str
    type: str | None = Field(
        default=None,
        description="Explicit step type: 'condition', 'sub_workflow', 'plan', 'loop', or 'aggregate'. "
        "Inferred as 'agent' or 'skill' from agent/skill fields when omitted.",
    )
    agent: str | None = None
    skill: str | None = None
    workflow: str | None = Field(
        default=None,
        description="Reference to a child workflow (name or ID). "
        "Sets resolved_type to 'sub_workflow'.",
    )
    goal: str | None = Field(
        default=None,
        description="Natural-language goal for dynamic step generation (type='plan').",
    )
    input: dict[str, Any] | None = None
    parallel_with: str | None = None
    recovery: RecoveryConfig | None = None
    when: list[StepConditionBranch] | None = None
    loop: LoopConfig | None = Field(
        default=None,
        description="Loop configuration for feedback cycle steps (type='loop').",
    )
    aggregate: AggregateConfig | None = Field(
        default=None,
        description="Aggregation configuration for fan-in steps (type='aggregate').",
    )

    @property
    def resolved_type(self) -> str:
        if self.type:
            return self.type
        if self.loop is not None:
            return "loop"
        if self.aggregate is not None:
            return "aggregate"
        if self.when is not None:
            return "condition"
        if self.workflow is not None:
            return "sub_workflow"
        if self.goal is not None:
            return "plan"
        if self.skill is not None:
            return "skill"
        return "agent"

    @property
    def target_ref(self) -> str | None:
        """The agent or skill reference string (may be a direct ID or 'search:...')."""
        return self.agent or self.skill


class WorkflowDef(BaseModel):
    name: str
    version: int = 1
    triggers: list[TriggerDef] | None = None
    steps: list[WorkflowStep]
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)
    max_duration_seconds: int | None = Field(
        default=None,
        description="Maximum wall-clock seconds for the entire workflow. "
        "Falls back to the system default when None.",
    )
    max_concurrent_executions: int | None = Field(
        default=None,
        description="Max parallel executions of this workflow definition.",
    )
    max_concurrent_per_agent: int | None = Field(
        default=None,
        description="Default cap on concurrent invocations of any single agent.",
    )
