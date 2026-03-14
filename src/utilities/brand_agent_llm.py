"""LLM utility for brand agent responses. Invoke runs inside Intuno; no external HTTP."""

from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from src.core.settings import settings
from src.models.brand import Brand

_LLM_CLIENT: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _LLM_CLIENT
    if _LLM_CLIENT is None:
        _LLM_CLIENT = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _LLM_CLIENT


_BRAND_CONTEXT_TEMPLATE = """Brand information (use only this to answer):
- Name: {name}
- Description: {description}
- Website: {website}
- Contact: {contact}"""

_SYSTEM_PROMPT_TEMPLATE = """You are the official voice of {brand_name}. Answer the user's question using ONLY the brand information provided below.

Guardrails:
- Use only the provided brand context. Do not invent, assume, or hallucinate information.
- If the user asks about something not in the context, politely say you don't have that information and suggest visiting the website or contacting them.
- Keep responses concise and professional.
- Do not generate harmful, offensive, or inappropriate content.
- Do not pretend to perform actions (book appointments, process payments, etc.); provide information only.

{brand_context}"""


async def generate_brand_agent_response(
    brand: Brand,
    user_input: Dict[str, Any],
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an LLM response for a brand agent invoke. Uses only brand context; no external knowledge.

    :param brand: Brand ORM
    :param user_input: Invoke request input dict (message, query, text, etc.)
    :param model: Optional model override; defaults to settings.BRAND_AGENT_LLM_MODEL
    :return: Dict with "message" key (compatible with broker response)
    """
    if not settings.OPENAI_API_KEY:
        return {
            "message": (
                f"Welcome! {brand.name}. "
                f"{brand.description or 'No additional description.'} "
                f"You can learn more at {brand.website or 'our website'}."
            ),
        }

    query = _extract_query(user_input)
    if not query or not query.strip():
        return {"message": f"Hello! I'm the official assistant for {brand.name}. How can I help you today?"}

    brand_context = _BRAND_CONTEXT_TEMPLATE.format(
        name=brand.name,
        description=brand.description or "Not provided.",
        website=brand.website or "Not provided.",
        contact=brand.verification_email or "Not provided.",
    )
    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        brand_name=brand.name,
        brand_context=brand_context,
    )

    used_model = model or getattr(settings, "BRAND_AGENT_LLM_MODEL", "gpt-4o-mini")
    client = _get_client()

    response = await client.chat.completions.create(
        model=used_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        temperature=0.3,
        max_tokens=500,
    )
    content = response.choices[0].message.content or ""
    return {"message": content.strip()}


def _extract_query(payload: Dict[str, Any]) -> str:
    """Extract user query from invoke input; mirrors broker _extract_text."""
    for key in ("message", "query", "text", "content", "prompt", "input"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""
