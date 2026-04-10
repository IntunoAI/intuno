"""Unit tests for convergence detectors."""

import pytest

from src.network.utils.convergence import (
    ApprovalDetector,
    MaxIterationsDetector,
    SimilarityDetector,
    create_detector,
)


class TestMaxIterationsDetector:
    @pytest.mark.asyncio
    async def test_converges_at_max(self):
        d = MaxIterationsDetector(max_iterations=3)
        assert not await d.has_converged(0, "out", None, {})
        assert not await d.has_converged(2, "out", "prev", {})
        assert await d.has_converged(3, "out", "prev", {})

    @pytest.mark.asyncio
    async def test_converges_beyond_max(self):
        d = MaxIterationsDetector(max_iterations=2)
        assert await d.has_converged(5, "out", "prev", {})


class TestApprovalDetector:
    @pytest.mark.asyncio
    async def test_detects_approved_string(self):
        d = ApprovalDetector()
        assert await d.has_converged(1, "This is approved.", None, {})

    @pytest.mark.asyncio
    async def test_detects_lgtm(self):
        d = ApprovalDetector()
        assert await d.has_converged(1, "LGTM, ship it!", None, {})

    @pytest.mark.asyncio
    async def test_detects_dict_approved_flag(self):
        d = ApprovalDetector()
        assert await d.has_converged(1, {"approved": True}, None, {})

    @pytest.mark.asyncio
    async def test_no_approval_in_text(self):
        d = ApprovalDetector()
        assert not await d.has_converged(1, "needs more work", None, {})

    @pytest.mark.asyncio
    async def test_dict_without_approved_key(self):
        d = ApprovalDetector()
        assert not await d.has_converged(1, {"output": "still working"}, None, {})

    @pytest.mark.asyncio
    async def test_non_string_non_dict(self):
        d = ApprovalDetector()
        assert not await d.has_converged(1, 42, None, {})


class TestSimilarityDetector:
    @pytest.mark.asyncio
    async def test_no_convergence_on_first_iteration(self):
        d = SimilarityDetector(threshold=0.95)
        assert not await d.has_converged(0, "hello world", None, {})

    @pytest.mark.asyncio
    async def test_identical_outputs_converge(self):
        d = SimilarityDetector(threshold=0.95)
        assert await d.has_converged(1, "hello world", "hello world", {})

    @pytest.mark.asyncio
    async def test_different_outputs_dont_converge(self):
        d = SimilarityDetector(threshold=0.95)
        assert not await d.has_converged(
            1, "completely different text", "hello world", {}
        )

    @pytest.mark.asyncio
    async def test_nearly_identical_converge(self):
        d = SimilarityDetector(threshold=0.7)
        text1 = "the quick brown fox jumps over the lazy dog"
        text2 = "the quick brown fox leaps over the lazy dog"
        # Jaccard: 7 shared words / 10 unique words = 0.7
        assert await d.has_converged(1, text1, text2, {})

    @pytest.mark.asyncio
    async def test_dict_output_extraction(self):
        d = SimilarityDetector(threshold=0.95)
        assert await d.has_converged(
            1,
            {"output": "same text here"},
            {"output": "same text here"},
            {},
        )

    @pytest.mark.asyncio
    async def test_empty_strings(self):
        d = SimilarityDetector(threshold=0.95)
        # Both empty — no convergence (empty check returns False)
        assert not await d.has_converged(1, "", "", {})


class TestCreateDetector:
    def test_creates_similarity(self):
        d = create_detector("similarity", {"threshold": 0.9})
        assert isinstance(d, SimilarityDetector)
        assert d.threshold == 0.9

    def test_creates_approval(self):
        d = create_detector("approval")
        assert isinstance(d, ApprovalDetector)

    def test_creates_max_iterations(self):
        d = create_detector("max_iterations", {"max_iterations": 10})
        assert isinstance(d, MaxIterationsDetector)
        assert d.max_iterations == 10

    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            create_detector("nonexistent")
