from types import SimpleNamespace

import pytest

from app.services.opportunity_discovery import (
    WEIGHTS,
    build_search_queries,
    calculate_opportunity_score,
    normalize_topic,
)
from app.services.search_provider import SearchProviderError, WebSearchProvider


def test_opportunity_score_uses_documented_weights():
    scores = {key: 100 for key in WEIGHTS}
    assert calculate_opportunity_score(scores) == 100.0
    assert round(sum(WEIGHTS.values()), 5) == 1.0


def test_opportunity_score_is_weighted_and_bounded_by_input():
    scores = {
        "audience_demand": 100,
        "monetization_fit": 0,
        "competition_gap": 0,
        "retention_potential": 0,
        "originality": 0,
        "production_feasibility": 0,
    }
    assert calculate_opportunity_score(scores) == 25.0


def test_topic_normalization_collapses_case_and_punctuation():
    assert normalize_topic("  The  Strange: History! ") == "the strange history"


def test_queries_are_derived_from_the_channel_not_other_niches():
    channel = SimpleNamespace(
        niche="Weird History",
        target_audience="curious adults",
        topic_boundaries=["forgotten inventions"],
        monetization_strategy={"research_keywords": ["museum discoveries"]},
    )
    queries = build_search_queries(channel, year=2026)
    assert all("Weird History" in query for query in queries)
    assert all("Finance" not in query for query in queries)
    assert any("forgotten inventions" in query for query in queries)
    assert any("museum discoveries" in query for query in queries)


@pytest.mark.asyncio
async def test_unknown_search_provider_fails_explicitly():
    provider = WebSearchProvider(provider="not-a-provider")
    with pytest.raises(SearchProviderError):
        await provider.search("test")
