"""Unit and integration tests for Phase 2: Multi-Platform Adaptation & Pre-Render Viral Potential Scoring."""

import pytest
from app.models.platforms import (
    SocialPlatform,
    PlatformSpec,
    PLATFORM_SPECS,
    PlatformAdaptedContent,
)
from app.agents.platform_adapter import PlatformAdapterAgent
from app.agents.viral_evaluator import (
    ViralEvaluatorAgent,
    ViralDecision,
    ViralScoreBreakdown,
)


def test_platform_specifications():
    """Verify technical and formatting constraints for all 6 target platforms."""
    assert SocialPlatform.YOUTUBE_SHORTS in PLATFORM_SPECS
    assert SocialPlatform.LINKEDIN in PLATFORM_SPECS
    assert SocialPlatform.X_THREAD in PLATFORM_SPECS
    assert SocialPlatform.TIKTOK in PLATFORM_SPECS

    shorts = PLATFORM_SPECS[SocialPlatform.YOUTUBE_SHORTS]
    assert shorts.aspect_ratio == "9:16"
    assert shorts.target_duration_seconds == 45

    linkedin = PLATFORM_SPECS[SocialPlatform.LINKEDIN]
    assert linkedin.aspect_ratio == "1:1"
    assert linkedin.caption_max_chars >= 3000

    x_thread = PLATFORM_SPECS[SocialPlatform.X_THREAD]
    assert x_thread.aspect_ratio == "16:9"


@pytest.mark.asyncio
async def test_platform_adapter_agent_generations():
    """Verify PlatformAdapterAgent creates tailored platform-native outputs."""
    adapter = PlatformAdapterAgent()
    
    # Adapt to LinkedIn (should include carousel slides)
    li_content = await adapter.adapt_content(
        master_title="Why AI Pipelines Stall",
        master_topic="Distributed AI Workflows",
        core_narrative="Workers need deterministic queues and database-level idempotency to prevent infinite loops and race conditions.",
        target_platform=SocialPlatform.LINKEDIN,
    )
    assert li_content.platform == SocialPlatform.LINKEDIN
    assert li_content.aspect_ratio == "1:1"
    assert li_content.carousel_slides is not None
    assert len(li_content.carousel_slides) >= 3

    # Adapt to X Thread (should include tweet list)
    x_content = await adapter.adapt_content(
        master_title="Why AI Pipelines Stall",
        master_topic="Distributed AI Workflows",
        core_narrative="Workers need deterministic queues and database-level idempotency to prevent infinite loops and race conditions.",
        target_platform=SocialPlatform.X_THREAD,
    )
    assert x_content.platform == SocialPlatform.X_THREAD
    assert x_content.thread_tweets is not None
    assert len(x_content.thread_tweets) >= 4
    assert any("1/" in t for t in x_content.thread_tweets)

    # Multi-platform full adaptation
    all_platforms = await adapter.adapt_to_all_platforms(
        master_title="Modern Concurrency",
        master_topic="Concurrency",
        core_narrative="Semaphore bounding prevents system thrashing.",
    )
    assert len(all_platforms) == 5
    assert SocialPlatform.TIKTOK in all_platforms


@pytest.mark.asyncio
async def test_viral_evaluator_priority_and_rewrite_gating():
    """Verify Pre-render Viral Potential scoring rubric and gating decisions."""
    evaluator = ViralEvaluatorAgent()

    # 1. High viral potential content with strong hook
    high_score = await evaluator.evaluate_script(
        title="Stop Building Clones",
        hook="Why 90% of AI agent startups will die in 6 months",
        script_text="Most founders are wrapping API endpoints and calling it an agent. Here is the operational moat you actually need.",
        target_duration=45,
    )
    assert high_score.overall_score >= 8.0
    assert high_score.decision == ViralDecision.PRIORITY_RENDER
    assert high_score.hook_score >= 8.5
    assert high_score.retention_score >= 8.5

    # 2. Weak content that triggers rewrite loop
    low_score = await evaluator.evaluate_script(
        title="Generic AI Update",
        hook="Hello everyone, today we talk about artificial intelligence",
        script_text="Please rewrite this because it has no substance and lacks curiosity.",
        target_duration=45,
    )
    assert low_score.overall_score < 7.0
    assert low_score.decision == ViralDecision.REWRITE_NEEDED
    assert len(low_score.actionable_improvements) > 0

    # 3. Standard acceptable content
    med_score = await evaluator.evaluate_script(
        title="Database Indexing Basics",
        hook="How to index foreign keys in PostgreSQL",
        script_text="A clean explanation of how B-tree indexes speed up your join operations.",
        target_duration=45,
    )
    assert 7.0 <= med_score.overall_score <= 8.0
    assert med_score.decision == ViralDecision.APPROVED
