"""Planner utility: goal + input -> list of steps.

Current (MVP): steps are not defined by an LLM. We produce a single step with
description=goal and input=merged goal+input. The Executor then uses semantic
discovery (embedding + vector search) to find which agent/capability fits that
one step.

When PLANNER_USE_LLM is True, plan_llm() decomposes the goal into multiple steps
via an LLM; get_plan() is the single async entry point used by the orchestrator.
See docs/HOW_ORCHESTRATOR_WORKS.md.
"""

import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from src.core.settings import settings

logger = logging.getLogger(__name__)

# OpenAI client for LLM planning (reuse same key as semantic enhancement)
_llm_client: Optional[AsyncOpenAI] = None


def _get_llm_client() -> AsyncOpenAI:
    global _llm_client
    if _llm_client is None:
        _llm_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _llm_client


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
    No LLM is used; for multi-step plans use get_plan() with PLANNER_USE_LLM=True.
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


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences (e.g. ```json ... ```) if present."""
    text = text.strip()
    match = re.search(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


async def plan_llm(goal: str, input_data: Dict[str, Any]) -> List[StepSpec]:
    """
    Decompose goal into multiple steps using an LLM. Returns JSON array of
    {description, input}; falls back to single-step plan on parse error or empty.
    :param goal: str - User goal
    :param input_data: dict - User input
    :return: List[StepSpec]
    """
    goal_stripped = (goal or "").strip()
    if not goal_stripped:
        return []

    input_json = json.dumps(input_data or {}, default=str)
    system_content = (
        "You are a task decomposition assistant. Given a user goal and optional context, "
        "output an ordered list of steps. Each step has a short description (used to find an AI agent) "
        "and optional input. Descriptions should be one sentence, action-oriented, and self-contained."
    )
    user_content = f"""Goal: {goal_stripped}

Context (optional): {input_json}

Output a single JSON array of steps. Each step: {{"description": "...", "input": {{}}}}
- description: one sentence, action-oriented (e.g. "Extract key figures from the document", "Translate the text to Spanish").
- input: optional key-value dict for that step; can be empty {{}}.

Return only the JSON array, e.g. [{{"description": "...", "input": {{}}}}, ...]. No other text."""

    try:
        client = _get_llm_client()
        response = await client.chat.completions.create(
            model=settings.PLANNER_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            logger.warning("Planner LLM returned empty response; falling back to single-step plan.")
            return plan(goal, input_data)

        raw = _strip_json_fences(raw)
        parsed = json.loads(raw)
        if not isinstance(parsed, list) or len(parsed) == 0:
            logger.warning("Planner LLM did not return a non-empty array; falling back to single-step plan.")
            return plan(goal, input_data)

        steps: List[StepSpec] = []
        for i, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            desc = item.get("description")
            if not desc or not str(desc).strip():
                continue
            step_input = item.get("input")
            if not isinstance(step_input, dict):
                step_input = {}
            # First step: ensure goal and user input_data are present for the agent
            if i == 0:
                step_input = {"goal": goal_stripped, **(input_data or {}), **step_input}
            steps.append(
                StepSpec(
                    id=uuid.uuid4(),
                    description=str(desc).strip(),
                    input=step_input,
                )
            )
        if not steps:
            logger.warning("Planner LLM returned no valid steps; falling back to single-step plan.")
            return plan(goal, input_data)
        return steps
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.warning("Planner LLM parse error: %s; falling back to single-step plan.", e)
        return plan(goal, input_data)
    except Exception as e:
        logger.warning("Planner LLM call failed: %s; falling back to single-step plan.", e)
        return plan(goal, input_data)


async def get_plan(goal: str, input_data: Dict[str, Any]) -> List[StepSpec]:
    """
    Single async entry point for the orchestrator. If PLANNER_USE_LLM is True,
    uses LLM to decompose into multiple steps; otherwise returns single-step plan.
    :param goal: str - User goal
    :param input_data: dict - User input
    :return: List[StepSpec]
    """
    if settings.PLANNER_USE_LLM:
        return await plan_llm(goal, input_data or {})
    return plan(goal, input_data or {})
