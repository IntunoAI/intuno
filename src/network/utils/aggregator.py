"""Fan-in aggregation strategies for combining outputs from multiple agents.

Used by the ``aggregate`` step type in the workflow orchestrator.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Aggregator(ABC):
    """Base class for aggregation strategies."""

    @abstractmethod
    async def aggregate(self, inputs: list[dict[str, Any]]) -> dict[str, Any]:
        """Combine multiple agent outputs into a single result."""
        ...


class MergeAggregator(Aggregator):
    """Concatenate all outputs into a single dict.

    Each input is keyed by its source step ID.
    """

    async def aggregate(self, inputs: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for item in inputs:
            source = item.get("source", f"input_{len(merged)}")
            merged[source] = item.get("output")
        return {"strategy": "merge", "result": merged}


class VoteAggregator(Aggregator):
    """Pick the majority answer for classification tasks.

    Each input should have an ``output`` field with a string value.
    The most common value wins.
    """

    async def aggregate(self, inputs: list[dict[str, Any]]) -> dict[str, Any]:
        votes: dict[str, int] = {}
        for item in inputs:
            output = item.get("output")
            key = str(output) if output is not None else "null"
            votes[key] = votes.get(key, 0) + 1

        if not votes:
            return {"strategy": "vote", "result": None, "votes": {}}

        winner = max(votes, key=votes.get)
        return {
            "strategy": "vote",
            "result": winner,
            "votes": votes,
            "total": len(inputs),
        }


class LLMSummarizeAggregator(Aggregator):
    """Use an LLM to synthesize all inputs into a coherent output.

    Falls back to merge if LLM is unavailable.
    """

    async def aggregate(self, inputs: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            from openai import AsyncOpenAI
            from src.core.settings import settings

            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

            formatted_inputs = "\n\n".join(
                f"[{item.get('source', f'Agent {i+1}')}]:\n{json.dumps(item.get('output'), indent=2)}"
                for i, item in enumerate(inputs)
            )

            response = await client.chat.completions.create(
                model=settings.LLM_ENHANCEMENT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a synthesizer. Multiple AI agents have provided their outputs. "
                            "Combine them into a single coherent, comprehensive response. "
                            "Resolve contradictions, merge complementary information, "
                            "and produce a unified result."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Synthesize these agent outputs:\n\n{formatted_inputs}",
                    },
                ],
                temperature=0.3,
            )

            synthesis = response.choices[0].message.content
            return {
                "strategy": "llm_summarize",
                "result": synthesis,
                "source_count": len(inputs),
            }
        except Exception as exc:
            logger.warning("LLM summarize failed, falling back to merge: %s", exc)
            fallback = MergeAggregator()
            result = await fallback.aggregate(inputs)
            result["strategy"] = "llm_summarize_fallback"
            return result


def create_aggregator(strategy: str) -> Aggregator:
    """Factory function for aggregation strategies."""
    if strategy == "merge":
        return MergeAggregator()
    elif strategy == "vote":
        return VoteAggregator()
    elif strategy == "llm_summarize":
        return LLMSummarizeAggregator()
    else:
        raise ValueError(f"Unknown aggregation strategy: {strategy}")
