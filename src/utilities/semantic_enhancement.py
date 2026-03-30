"""Semantic enhancement utility for LLM-based text enhancement."""

from typing import Dict, List, Any, Optional

from src.core.settings import settings

# Lazy-initialized OpenAI client (avoids crash when OPENAI_API_KEY is empty)
_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        from openai import AsyncOpenAI
        _llm_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _llm_client


class SemanticEnhancementService:
    """Service for enhancing text using LLM before embedding generation."""

    def __init__(self, enabled: bool = True, model: str = "gpt-4o-mini"):
        self.enabled = enabled
        self.model = model

    async def enhance_agent_text(
        self,
        agent_name: str,
        description: str,
        tags: List[str],
        input_schema: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Enhance agent text using LLM for better semantic search.

        Generates enriched text with expanded descriptions, semantic keywords,
        use cases, and synonyms to improve discoverability.

        :param agent_name: Agent name
        :param description: Agent description
        :param tags: List of tags
        :param input_schema: Optional input schema for additional context
        :return: Enhanced text for embedding generation
        """
        tags_text = ", ".join(tags) if tags else ""

        if not self.enabled:
            parts = [f"{agent_name}.", description]
            if tags_text:
                parts.append(f"Tags: {tags_text}")
            return " ".join(parts).strip()

        # Build input schema summary if available
        schema_text = ""
        if input_schema and input_schema.get("properties"):
            props = ", ".join(
                f"{k}: {v.get('description', v.get('type', k))}"
                for k, v in input_schema["properties"].items()
            )
            schema_text = f"\nAccepts: {props}"

        prompt = f"""You are helping to create an enhanced text description for an AI agent for semantic search.

Agent Name: {agent_name}
Description: {description}
Tags: {tags_text or "None"}{schema_text}

Generate an enhanced, comprehensive text description that:
1. Expands on the original description with more detail
2. Includes semantic keywords and related concepts
3. Describes potential use cases and scenarios
4. Incorporates synonyms and alternative phrasings
5. Makes the agent more discoverable through semantic search

Return only the enhanced text, without any additional commentary or formatting."""

        try:
            response = await _get_llm_client().chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a semantic search enhancement assistant. Generate enhanced text descriptions that improve discoverability through semantic search.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            parts = [f"{agent_name}.", description]
            if tags_text:
                parts.append(f"Tags: {tags_text}")
            return " ".join(parts).strip()

    async def enhance_discovery_query(self, query: str) -> str:
        """Enhance discovery query using LLM for better semantic search.

        :param query: User's natural language query
        :return: Enhanced query text for embedding
        """
        if not self.enabled:
            return query

        prompt = f"""You are helping to enhance a search query for semantic discovery of AI agents.

Original Query: {query}

Generate an enhanced version of this query that:
1. Expands with synonyms and related terms
2. Includes alternative phrasings and variations
3. Extracts key concepts and intent
4. Makes the query more effective for semantic search

Return only the enhanced query text, without any additional commentary or formatting."""

        try:
            response = await _get_llm_client().chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a semantic search query enhancement assistant. Generate enhanced queries that improve search results through better semantic matching.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return query
