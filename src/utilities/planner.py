"""Planner utility: goal + input -> list of steps.

Current (MVP): steps are not defined by an LLM. We produce a single step with
description=goal and input=merged goal+input. The Executor then uses semantic
discovery (embedding + vector search) to find which agent/capability fits that
one step.

Future: an LLM-based planner can decompose a goal into multiple steps (e.g.
"extract data" -> "translate" -> "summarize"). Each step would have a
description and optional input; the same Executor would run each step via
discovery + Broker. See docs/HOW_ORCHESTRATOR_WORKS.md.
"""

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class StepSpec:
    """Single step in a plan: id, description, and optional input for the step."""

    id: uuid.UUID
    description: str
    input: Dict[str, Any]


def plan(goal: str, input_data: Dict[str, Any]) -> List[StepSpec]:
    """
    Produce a plan (list of steps) from goal and input.
    MVP: single step with description=goal and input merged from goal + input_data.
    No LLM is used; for multi-step plans, a future LLM planner would replace this.
    Empty goal yields empty plan (orchestrator will treat as failure).
    :param goal: str - User goal
    :param input_data: dict - User input
    :return: List[StepSpec]
    """
    goal_stripped = (goal or "").strip()
    if not goal_stripped:
        return []

    # Single step: merge goal into input for the step
    step_input = {"goal": goal_stripped, **(input_data or {})}
    step = StepSpec(
        id=uuid.uuid4(),
        description=goal_stripped,
        input=step_input,
    )
    return [step]
