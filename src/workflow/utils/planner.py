"""Dynamic step planner — an LLM generates workflow steps at runtime.

Given a natural-language goal and the current execution context, the
planner produces a list of ``WorkflowStep``-compatible dicts that are
validated, converted to step objects, and injected into the running DAG.

The planner calls wisdom's BrokerService directly to invoke the
system task-planner agent (no intuno-sdk indirection).

The planner enforces guardrails:

- Maximum generated steps (``max_plan_steps``, default 10)
- No recursive ``plan`` steps in generated output
- Timeout on planner call (``plan_timeout_seconds``, default 30)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.workflow.exceptions import StepExecutionError
from src.workflow.models.dsl import WorkflowStep

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 10
PLAN_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = """\
You are a workflow planner for an AI agent orchestration system.
Given a goal and context, produce a JSON array of workflow steps.

Each step must have:
- "id": unique string identifier
- "agent" or "skill": either a direct agent ID or "search:<natural language query>"
- "input": dict of input parameters (may use template syntax like {{ trigger.field }})

Optionally:
- "parallel_with": id of another step to run concurrently
- "when": conditional branches (list of {if/else, goto} objects)

Rules:
- Do NOT produce steps with type "plan" (no recursive planning)
- Keep the plan minimal — prefer fewer, well-targeted steps
- Use "search:<query>" when you don't know the exact agent ID
- Maximum {max_steps} steps

Respond ONLY with a valid JSON array. No markdown, no explanation.
"""


class Planner:
    def __init__(self) -> None:
        pass

    async def generate_steps(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        max_steps: int = MAX_PLAN_STEPS,
        timeout: float = PLAN_TIMEOUT_SECONDS,
    ) -> list[WorkflowStep]:
        """Call the planner and return validated WorkflowStep objects."""
        prompt = self._build_prompt(goal, context, max_steps)

        try:
            raw_steps = await asyncio.wait_for(
                self._call_planner(prompt, goal),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise StepExecutionError(
                f"Planner timed out after {timeout}s for goal: {goal}"
            )

        return self._validate_steps(raw_steps, max_steps)

    async def _call_planner(self, prompt: str, goal: str) -> list[dict[str, Any]]:
        """Invoke the task-planner agent via wisdom's BrokerService directly."""
        from src.database import async_session_factory
        from src.services.broker import BrokerService
        from src.repositories.broker import BrokerConfigRepository
        from src.repositories.invocation_log import InvocationLogRepository
        from src.repositories.registry import RegistryRepository
        from src.repositories.conversation import ConversationRepository
        from src.repositories.message import MessageRepository
        from src.repositories.brand import BrandRepository
        from src.schemas.broker import InvokeRequest
        from src.models.auth import User
        from sqlalchemy import select

        try:
            async with async_session_factory() as session:
                broker = BrokerService(
                    invocation_log_repository=InvocationLogRepository(session),
                    broker_config_repository=BrokerConfigRepository(session),
                    registry_repository=RegistryRepository(session),
                    conversation_repository=ConversationRepository(session),
                    message_repository=MessageRepository(session),
                    brand_repository=BrandRepository(session),
                )
                result = await session.execute(select(User).limit(1))
                system_user = result.scalar_one_or_none()
                if not system_user:
                    raise StepExecutionError("No system user found for planner invocation")

                invoke_req = InvokeRequest(
                    agent_id="system:task-planner",
                    input={
                        "system_prompt": prompt,
                        "goal": goal,
                    },
                )
                response = await broker.invoke_agent(invoke_req, caller_user_id=system_user.id)
                await session.commit()

            data = response.data

            if isinstance(data, str):
                steps = json.loads(data)
            elif isinstance(data, dict) and "steps" in data:
                steps = data["steps"]
            elif isinstance(data, list):
                steps = data
            else:
                raise StepExecutionError(
                    f"Planner returned unexpected format: {type(data)}"
                )

            if not isinstance(steps, list):
                raise StepExecutionError("Planner did not return a list of steps")

            return steps
        except StepExecutionError:
            raise
        except Exception as exc:
            raise StepExecutionError(
                f"Planner invocation failed: {exc}"
            ) from exc

    def _validate_steps(
        self, raw_steps: list[dict[str, Any]], max_steps: int,
    ) -> list[WorkflowStep]:
        """Parse, validate, and enforce guardrails on generated steps."""
        if len(raw_steps) > max_steps:
            logger.warning(
                "Planner returned %d steps, truncating to %d",
                len(raw_steps), max_steps,
            )
            raw_steps = raw_steps[:max_steps]

        validated: list[WorkflowStep] = []
        seen_ids: set[str] = set()

        for i, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                logger.warning("Skipping non-dict step at index %d", i)
                continue

            if raw.get("type") == "plan" or raw.get("goal"):
                logger.warning(
                    "Rejecting recursive plan step '%s'", raw.get("id", f"step-{i}"),
                )
                continue

            if "id" not in raw:
                raw["id"] = f"planned-{i}"

            if raw["id"] in seen_ids:
                raw["id"] = f"{raw['id']}-{i}"
            seen_ids.add(raw["id"])

            try:
                step = WorkflowStep.model_validate(raw)
                validated.append(step)
            except Exception as exc:
                logger.warning("Invalid generated step '%s': %s", raw.get("id"), exc)
                continue

        if not validated:
            raise StepExecutionError("Planner produced no valid steps")

        return validated

    def _build_prompt(
        self, goal: str, context: dict[str, Any] | None, max_steps: int,
    ) -> str:
        prompt = SYSTEM_PROMPT.format(max_steps=max_steps)
        if context:
            prompt += f"\n\nCurrent execution context:\n{json.dumps(context, indent=2, default=str)}"
        prompt += f"\n\nGoal: {goal}"
        return prompt
