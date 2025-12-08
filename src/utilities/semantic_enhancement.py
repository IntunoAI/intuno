"""Semantic enhancement utility for LLM-based text enhancement."""

from typing import Dict, List, Any

from openai import AsyncOpenAI

from src.core.settings import settings

# Initialize OpenAI client for LLM calls
llm_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class SemanticEnhancementService:
    """Service for enhancing text using LLM before embedding generation."""

    def __init__(self, enabled: bool = True, model: str = "gpt-4o-mini"):
        """Initialize semantic enhancement service.
        :param enabled: Whether LLM enhancement is enabled
        :param model: OpenAI model to use for enhancement
        """
        self.enabled = enabled
        self.model = model

    async def enhance_manifest_text(
        self,
        agent_name: str,
        description: str,
        tags: List[str],
        capabilities: List[Dict[str, Any]],
    ) -> str:
        """Enhance agent manifest text using LLM for better semantic search.
        
        Takes agent manifest information and uses LLM to generate enriched text
        with expanded descriptions, semantic keywords, use case scenarios, and
        related concepts.
        
        :param agent_name: Agent name
        :param description: Agent description
        :param tags: List of tags
        :param capabilities: List of capability dictionaries
        :return: Enhanced text for embedding generation
        """
        if not self.enabled:
            # Return basic concatenation if enhancement is disabled
            tags_text = ", ".join(tags) if tags else ""
            return f"{agent_name}. {description}. Tags: {tags_text}".strip()

        # Prepare capabilities summary
        capabilities_summary = []
        for cap in capabilities:
            cap_id = cap.get("id", "")
            input_desc = cap.get("input_schema", {}).get("description", "")
            output_desc = cap.get("output_schema", {}).get("description", "")
            capabilities_summary.append(
                f"Capability {cap_id}: Input - {input_desc}, Output - {output_desc}"
            )
        capabilities_text = " | ".join(capabilities_summary) if capabilities_summary else "No capabilities"

        tags_text = ", ".join(tags) if tags else "No tags"

        # Create prompt for LLM enhancement
        prompt = f"""You are helping to create an enhanced text description for an AI agent that will be used for semantic search.

Agent Name: {agent_name}
Description: {description}
Tags: {tags_text}
Capabilities: {capabilities_text}

Generate an enhanced, comprehensive text description that:
1. Expands on the original description with more detail
2. Includes semantic keywords and related concepts
3. Describes potential use cases and scenarios
4. Incorporates synonyms and alternative phrasings
5. Makes the agent more discoverable through semantic search

Return only the enhanced text, without any additional commentary or formatting."""

        try:
            response = await llm_client.chat.completions.create(
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
            enhanced_text = response.choices[0].message.content.strip()
            return enhanced_text
        except Exception:
            # Fallback to basic text if LLM call fails
            tags_text = ", ".join(tags) if tags else ""
            return f"{agent_name}. {description}. Tags: {tags_text}".strip()

    async def enhance_discovery_query(self, query: str) -> str:
        """Enhance discovery query using LLM for better semantic search.
        
        Takes user's natural language query and uses LLM to expand it with
        synonyms, related terms, query variations, and extract key concepts.
        
        :param query: User's natural language query
        :return: Enhanced query text for embedding
        """
        if not self.enabled:
            return query

        # Create prompt for query enhancement
        prompt = f"""You are helping to enhance a search query for semantic discovery of AI agents.

Original Query: {query}

Generate an enhanced version of this query that:
1. Expands with synonyms and related terms
2. Includes alternative phrasings and variations
3. Extracts key concepts and intent
4. Makes the query more effective for semantic search

Return only the enhanced query text, without any additional commentary or formatting."""

        try:
            response = await llm_client.chat.completions.create(
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
            enhanced_query = response.choices[0].message.content.strip()
            return enhanced_query
        except Exception:
            # Fallback to original query if LLM call fails
            return query

