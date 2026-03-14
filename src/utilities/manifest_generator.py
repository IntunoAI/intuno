"""LLM utility for generating agent configurations from natural language descriptions."""

import json
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from src.core.settings import settings
from src.schemas.registry import AgentRegistration

_LLM_CLIENT: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        _LLM_CLIENT = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _LLM_CLIENT


_SYSTEM_PROMPT = """You generate agent configurations from user descriptions. Output ONLY valid JSON. No markdown, no code blocks, no explanation.

Schema:
- name: string (human-readable agent name)
- description: string (what the agent does)
- endpoint: string (invoke URL; use "https://example.com/invoke" if unknown)
- auth_type: string, one of: "public" | "api_key" | "bearer_token" (default "public")
- input_schema: JSON Schema object with type "object" and properties describing what the endpoint accepts. Must have at least one property. Format: {"type": "object", "properties": {"field": {"type": "string", "description": "..."}}, "required": ["field"]}
- tags: array of strings (relevant keywords)

Rules:
- Default auth_type to "public" unless the user mentions API key, bearer token, or authentication.
- ALWAYS include input_schema with non-empty properties. Infer from the description what input the agent expects.
- If the user provides a URL, use it for endpoint.
- Generate descriptive tags from the description.

Example (weather):
{
  "name": "Weather Agent",
  "description": "Provides current weather and forecasts for any city",
  "endpoint": "https://api.weather.com/invoke",
  "auth_type": "api_key",
  "input_schema": {
    "type": "object",
    "properties": {
      "city": {"type": "string", "description": "City name to get weather for"}
    },
    "required": ["city"]
  },
  "tags": ["weather", "forecast", "climate"]
}

Example (calculator):
{
  "name": "Calculator Agent",
  "description": "Performs basic math operations: addition, subtraction, multiplication, division",
  "endpoint": "https://calc.example.com/invoke",
  "auth_type": "public",
  "input_schema": {
    "type": "object",
    "properties": {
      "operation": {"type": "string", "description": "Math operation: add, subtract, multiply, divide"},
      "a": {"type": "number", "description": "First operand"},
      "b": {"type": "number", "description": "Second operand"}
    },
    "required": ["operation", "a", "b"]
  },
  "tags": ["math", "calculator", "arithmetic"]
}"""


class ManifestGenerationError(Exception):
    """Raised when agent config generation fails."""
    pass


async def generate_agent_from_description(
    description: str,
    endpoint: Optional[str] = None,
) -> AgentRegistration:
    """
    Generate an agent configuration from a natural language description.

    :param description: User's description of their agent
    :param endpoint: Optional known invoke URL
    :return: Validated AgentRegistration
    :raises ManifestGenerationError: If API key missing, LLM fails, or output invalid
    """
    if not settings.OPENAI_API_KEY or not settings.OPENAI_API_KEY.strip():
        raise ManifestGenerationError("AI generation requires OpenAI API key")

    client = _get_client()

    hints = ""
    if endpoint:
        hints += f"\nUse this URL for endpoint: {endpoint}"

    user_prompt = f"""Generate an agent configuration from this description:

{description}{hints}

IMPORTANT: Include input_schema with at least one property describing what the endpoint expects. Infer from the description.

Output only the JSON, nothing else."""

    try:
        response = await client.chat.completions.create(
            model=getattr(settings, "LLM_ENHANCEMENT_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise ManifestGenerationError(f"LLM call failed: {e}") from e

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ManifestGenerationError("LLM returned empty response")

    content = content.strip()
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]
        content = content.strip()

    try:
        raw: Dict[str, Any] = json.loads(content)
    except json.JSONDecodeError as e:
        raise ManifestGenerationError(f"Invalid JSON from LLM: {e}") from e

    try:
        return AgentRegistration.model_validate(raw)
    except Exception as e:
        raise ManifestGenerationError(f"Agent config validation failed: {e}") from e


# Keep old name as alias for backward compatibility with any internal callers
generate_manifest_from_description = generate_agent_from_description
