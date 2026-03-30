"""Parse a YAML (or dict) workflow definition into validated Pydantic models
and build the step dependency graph."""

from __future__ import annotations

from typing import Any

import yaml

from src.workflow.exceptions import DSLParseError
from src.workflow.models.dsl import WorkflowDef


def parse_yaml(raw: str) -> WorkflowDef:
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise DSLParseError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise DSLParseError("Workflow definition must be a YAML mapping")
    return parse_dict(data)


def parse_dict(data: dict[str, Any]) -> WorkflowDef:
    try:
        wf = WorkflowDef.model_validate(data)
    except Exception as exc:
        raise DSLParseError(f"Workflow validation failed: {exc}") from exc
    _validate_step_refs(wf)
    _detect_cycles(wf)
    return wf


def build_dependency_graph(wf: WorkflowDef) -> dict[str, list[str]]:
    """Return a mapping of step_id -> list of step_ids it depends on.

    Sequential steps depend on the previous step.  `parallel_with` merges
    two steps into the same dependency tier (they share the same
    predecessor rather than one depending on the other).
    """
    step_ids = {s.id for s in wf.steps}
    parallel_peers: dict[str, str] = {}
    for step in wf.steps:
        if step.parallel_with and step.parallel_with in step_ids:
            parallel_peers[step.id] = step.parallel_with

    deps: dict[str, list[str]] = {s.id: [] for s in wf.steps}
    prev: str | None = None
    for step in wf.steps:
        if step.id in parallel_peers:
            peer = parallel_peers[step.id]
            deps[step.id] = list(deps.get(peer, []))
        elif prev is not None:
            deps[step.id].append(prev)

        if step.id not in parallel_peers.values():
            prev = step.id

    for step in wf.steps:
        if step.when:
            for branch in step.when:
                if branch.goto in deps:
                    deps[branch.goto].append(step.id)

    return deps


def topological_order(deps: dict[str, list[str]]) -> list[list[str]]:
    """Return steps grouped into execution tiers (each tier can run in parallel)."""
    remaining = {k: set(v) for k, v in deps.items()}
    order: list[list[str]] = []

    while remaining:
        tier = [k for k, v in remaining.items() if not v]
        if not tier:
            raise DSLParseError(
                f"Cycle detected among steps: {list(remaining.keys())}"
            )
        order.append(sorted(tier))
        for k in tier:
            del remaining[k]
        for v in remaining.values():
            v -= set(tier)

    return order


def _validate_step_refs(wf: WorkflowDef) -> None:
    step_ids = {s.id for s in wf.steps}
    for step in wf.steps:
        if step.parallel_with and step.parallel_with not in step_ids:
            raise DSLParseError(
                f"Step '{step.id}' references unknown parallel_with target '{step.parallel_with}'"
            )
        if step.when:
            for branch in step.when:
                if branch.goto not in step_ids:
                    raise DSLParseError(
                        f"Step '{step.id}' condition goto '{branch.goto}' does not exist"
                    )
        if step.resolved_type == "sub_workflow" and not step.workflow:
            raise DSLParseError(
                f"Sub-workflow step '{step.id}' must have a 'workflow' field"
            )
        if step.resolved_type == "plan" and not step.goal:
            raise DSLParseError(
                f"Plan step '{step.id}' must have a 'goal' field"
            )


def _detect_cycles(wf: WorkflowDef) -> None:
    deps = build_dependency_graph(wf)
    topological_order(deps)
