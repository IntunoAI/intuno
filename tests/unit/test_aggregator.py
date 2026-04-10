"""Unit tests for aggregation strategies."""

import pytest

from src.network.utils.aggregator import (
    LLMSummarizeAggregator,
    MergeAggregator,
    VoteAggregator,
    create_aggregator,
)


class TestMergeAggregator:
    @pytest.mark.asyncio
    async def test_merges_by_source(self):
        agg = MergeAggregator()
        result = await agg.aggregate([
            {"source": "agent_1", "output": "Result A"},
            {"source": "agent_2", "output": "Result B"},
        ])
        assert result["strategy"] == "merge"
        assert result["result"]["agent_1"] == "Result A"
        assert result["result"]["agent_2"] == "Result B"

    @pytest.mark.asyncio
    async def test_auto_keys_without_source(self):
        agg = MergeAggregator()
        result = await agg.aggregate([
            {"output": "Result A"},
            {"output": "Result B"},
        ])
        assert result["strategy"] == "merge"
        assert len(result["result"]) == 2

    @pytest.mark.asyncio
    async def test_empty_inputs(self):
        agg = MergeAggregator()
        result = await agg.aggregate([])
        assert result["strategy"] == "merge"
        assert result["result"] == {}


class TestVoteAggregator:
    @pytest.mark.asyncio
    async def test_majority_wins(self):
        agg = VoteAggregator()
        result = await agg.aggregate([
            {"output": "yes"},
            {"output": "yes"},
            {"output": "no"},
        ])
        assert result["strategy"] == "vote"
        assert result["result"] == "yes"
        assert result["total"] == 3

    @pytest.mark.asyncio
    async def test_tie_picks_one(self):
        agg = VoteAggregator()
        result = await agg.aggregate([
            {"output": "a"},
            {"output": "b"},
        ])
        assert result["strategy"] == "vote"
        assert result["result"] in ("a", "b")

    @pytest.mark.asyncio
    async def test_empty_inputs(self):
        agg = VoteAggregator()
        result = await agg.aggregate([])
        assert result["strategy"] == "vote"
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_none_outputs(self):
        agg = VoteAggregator()
        result = await agg.aggregate([
            {"output": None},
            {"output": None},
        ])
        assert result["strategy"] == "vote"
        assert result["result"] == "null"


class TestLLMSummarizeAggregator:
    @pytest.mark.asyncio
    async def test_falls_back_to_merge_on_error(self):
        """Without a real OpenAI key, should fall back to merge."""
        agg = LLMSummarizeAggregator()
        result = await agg.aggregate([
            {"source": "agent_1", "output": "Result A"},
            {"source": "agent_2", "output": "Result B"},
        ])
        # Should fall back since no API key is set in tests
        assert result["strategy"] == "llm_summarize_fallback"
        assert "result" in result


class TestCreateAggregator:
    def test_creates_merge(self):
        assert isinstance(create_aggregator("merge"), MergeAggregator)

    def test_creates_vote(self):
        assert isinstance(create_aggregator("vote"), VoteAggregator)

    def test_creates_llm_summarize(self):
        assert isinstance(create_aggregator("llm_summarize"), LLMSummarizeAggregator)

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown"):
            create_aggregator("nonexistent")
