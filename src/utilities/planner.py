"""Planner utility: goal + input -> list of steps (MVP: single step)."""

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
