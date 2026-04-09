"""Convergence detectors for feedback loops.

Determine when iterative agent interactions have converged and should
stop.  Used by the loop step type in the workflow orchestrator.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class ConvergenceDetector(ABC):
    """Base class for convergence detection strategies."""

    @abstractmethod
    async def has_converged(
        self,
        iteration: int,
        current_output: Any,
        previous_output: Any,
        context: dict[str, Any],
    ) -> bool:
        """Return True if the loop should stop."""
        ...


class MaxIterationsDetector(ConvergenceDetector):
    """Hard cap on iterations — always enforced as a safety net."""

    def __init__(self, max_iterations: int = 5):
        self.max_iterations = max_iterations

    async def has_converged(
        self,
        iteration: int,
        current_output: Any,
        previous_output: Any,
        context: dict[str, Any],
    ) -> bool:
        return iteration >= self.max_iterations


class ApprovalDetector(ConvergenceDetector):
    """Check if the output contains an explicit approval signal.

    Looks for keywords like "approved", "accepted", "lgtm" in the output
    or for a structured ``{"approved": true}`` field.
    """

    APPROVAL_KEYWORDS = {"approved", "accepted", "lgtm", "looks good", "ship it"}

    async def has_converged(
        self,
        iteration: int,
        current_output: Any,
        previous_output: Any,
        context: dict[str, Any],
    ) -> bool:
        if isinstance(current_output, dict):
            if current_output.get("approved") is True:
                return True
            text = str(current_output.get("output", "")) + str(
                current_output.get("content", "")
            )
        elif isinstance(current_output, str):
            text = current_output
        else:
            return False

        text_lower = text.lower()
        return any(kw in text_lower for kw in self.APPROVAL_KEYWORDS)


class SimilarityDetector(ConvergenceDetector):
    """Compare consecutive outputs using text similarity.

    Uses a simple token overlap ratio (Jaccard similarity).  For
    production use, this could be upgraded to use embedding cosine
    similarity via the EmbeddingService.
    """

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold

    async def has_converged(
        self,
        iteration: int,
        current_output: Any,
        previous_output: Any,
        context: dict[str, Any],
    ) -> bool:
        if previous_output is None:
            return False

        current_text = self._to_text(current_output)
        previous_text = self._to_text(previous_output)

        if not current_text or not previous_text:
            return False

        similarity = self._jaccard_similarity(current_text, previous_text)
        logger.debug(
            "Similarity check: iteration=%d similarity=%.3f threshold=%.3f",
            iteration,
            similarity,
            self.threshold,
        )
        return similarity >= self.threshold

    def _to_text(self, output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            return str(output.get("output", "")) or str(output.get("content", ""))
        return str(output)

    def _jaccard_similarity(self, a: str, b: str) -> float:
        tokens_a = set(a.lower().split())
        tokens_b = set(b.lower().split())
        if not tokens_a and not tokens_b:
            return 1.0
        intersection = tokens_a & tokens_b
        union = tokens_a | tokens_b
        return len(intersection) / len(union) if union else 1.0


def create_detector(
    detector_type: str,
    config: dict[str, Any] | None = None,
) -> ConvergenceDetector:
    """Factory function for convergence detectors."""
    config = config or {}
    if detector_type == "similarity":
        return SimilarityDetector(threshold=config.get("threshold", 0.95))
    elif detector_type == "approval":
        return ApprovalDetector()
    elif detector_type == "max_iterations":
        return MaxIterationsDetector(
            max_iterations=config.get("max_iterations", 5)
        )
    else:
        raise ValueError(f"Unknown convergence detector type: {detector_type}")
