"""Unit and integration tests for Phase 3: Source Repurposing & Editorial Memory Learning Loop."""

import pytest
from app.services.source_ingestion import SourceIngestionService, SourceType
from app.agents.repurpose_agent import RepurposeAgent, RepurposingPlan
from app.services.editorial_memory import (
    EditorialMemoryService,
    FeedbackCategory,
    EditorialTasteProfile,
)


def test_source_ingestion_service():
    """Verify raw text ingestion, cleaning, and semantic chunking."""
    raw_html = """
    <h1>Building Resilient AI Workflows</h1>
    <p>Most AI prototypes look impressive in a Jupyter notebook.</p>
    <p>However, when deployed at scale, concurrency deadlocks and unhandled retries destroy system throughput.</p>
    """
    doc = SourceIngestionService.ingest_text(
        title="Building Resilient AI Workflows",
        text=raw_html,
        source_type=SourceType.ARTICLE_URL,
    )

    assert doc.title == "Building Resilient AI Workflows"
    assert "<p>" not in doc.raw_text
    assert doc.word_count > 15
    assert "concurrency deadlocks" in doc.raw_text

    chunks = SourceIngestionService.chunk_document(doc, max_words_per_chunk=10)
    assert len(chunks) >= 2


@pytest.mark.asyncio
async def test_repurpose_agent_generates_derived_shorts():
    """Verify RepurposeAgent mines claims and produces standalone short concepts."""
    agent = RepurposeAgent()
    doc = SourceIngestionService.ingest_text(
        title="High Throughput Distributed Pipelines",
        text="A detailed transcript discussing Redis task queues, PostgreSQL lock safety, and automated recovery.",
    )

    plan: RepurposingPlan = await agent.repurpose(doc=doc, short_count=3)
    assert plan.source_title == "High Throughput Distributed Pipelines"
    assert len(plan.key_moments) >= 2
    assert len(plan.derived_shorts) == 3

    # Check first short properties
    short1 = plan.derived_shorts[0]
    assert short1.title
    assert short1.hook
    assert short1.suggested_duration in [40, 45, 50]
    assert short1.source_reference == "High Throughput Distributed Pipelines"


def test_editorial_memory_learning_loop():
    """Verify human correction feedback updates creator taste profile and prompt guidelines."""
    memory = EditorialMemoryService.get_instance()
    
    # 1. Record hook correction
    memory.record_hook_correction(
        original_hook="AI agents are changing software development.",
        user_hook="Most AI agent projects are completely useless in production.",
        topic="AI Agents",
    )

    # 2. Record visual rejection reason
    memory.record_visual_rejection(
        reason="Too generic stock office photography",
        topic="B-roll",
    )

    # 3. Record voice feedback
    memory.record_voice_feedback("Tone is too robotic; increase conversational cadence")

    profile = memory.get_profile()
    assert profile.total_feedback_count >= 3
    assert any("Contrarian" in s for s in profile.preferred_hook_styles)
    assert "Too generic stock office photography" in profile.banned_visual_tropes
    assert "Tone is too robotic; increase conversational cadence" in profile.voice_guidance

    # 4. Injected guidelines string contains the learned preferences
    guidelines = memory.get_editorial_guidelines()
    assert "LEARNED CREATOR EDITORIAL TASTE GUIDELINES" in guidelines
    assert "Too generic stock office photography" in guidelines
    assert "robotic" in guidelines
