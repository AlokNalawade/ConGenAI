import pytest
from unittest.mock import AsyncMock

from app.agents.script import ScriptAgent
from app.models.ai_contracts import ScriptResult, validate_ai_response


def sample_package():
    return {
        "hook": "Oxford was teaching before the Aztec Empire existed.",
        "body": "Teaching was taking place in Oxford by 1096. Tenochtitlan was founded around 1325, while the Aztec Empire emerged around 1428.",
        "cta": "Which timeline surprised you most?",
        "estimated_duration": 40,
        "word_count": 25,
        "on_screen_captions": ["Oxford: teaching by 1096", "Tenochtitlan founded c. 1325", "Aztec Empire c. 1428"],
        "scene_beats": [
            {"scene_number": 1, "start_second": 0, "end_second": 5, "narration": "Oxford was teaching before the Aztec Empire existed.", "visual_prompt": "Cinematic aerial of medieval Oxford, historically grounded architecture.", "onscreen_text": "Oxford, by 1096"},
            {"scene_number": 2, "start_second": 5, "end_second": 20, "narration": "Teaching was taking place in Oxford by 1096.", "visual_prompt": "Medieval scholars studying manuscripts in a stone room.", "onscreen_text": "Teaching by 1096"},
            {"scene_number": 3, "start_second": 20, "end_second": 32, "narration": "Tenochtitlan was founded around 1325.", "visual_prompt": "Early Tenochtitlan on Lake Texcoco, canoes and causeways.", "onscreen_text": "Founded c. 1325"},
            {"scene_number": 4, "start_second": 32, "end_second": 40, "narration": "The Aztec Empire emerged around 1428.", "visual_prompt": "Panoramic view of Tenochtitlan with canals and markets.", "onscreen_text": "Empire c. 1428"},
        ],
        "factual_claims": ["Oxford teaching is documented by 1096", "Tenochtitlan was founded around 1325", "The Aztec Empire emerged around 1428"],
        "verification_notes": ["Verify dates against reliable historical sources before publication."],
        "caption": "Oxford's teaching history predates the Aztec Empire. Which date surprised you most?",
        "hashtags": ["#History", "#WeirdHistory"],
    }


def test_script_result_accepts_full_short_form_package():
    result = validate_ai_response(sample_package(), ScriptResult)
    assert len(result.scene_beats) == 4
    assert result.scene_beats[-1].end_second == 40
    assert result.factual_claims
    assert result.verification_notes
    assert result.caption.endswith("?")


@pytest.mark.asyncio
async def test_script_agent_passes_target_and_validates_scene_coverage():
    agent = ScriptAgent()
    agent.run = AsyncMock(return_value=sample_package())
    agent_log = AsyncMock()

    from app.core import logging as logging_module
    original_broadcast = logging_module.log_manager.broadcast
    logging_module.log_manager.broadcast = agent_log
    try:
        result = await agent.generate_script(
            research_data={"summary": "Test topic", "sources": ["https://example.org/source"]},
            platform="YouTube Shorts",
            target_duration=40,
        )
    finally:
        logging_module.log_manager.broadcast = original_broadcast

    assert result.estimated_duration == 40
    assert len(result.scene_beats) == 4
    prompt = agent.run.await_args.args[1]
    assert "Target duration seconds: 40" in prompt


@pytest.mark.asyncio
async def test_script_agent_rejects_uncovered_scene_timeline():
    agent = ScriptAgent()
    package = sample_package()
    package["scene_beats"][-1]["start_second"] = 34
    package["scene_beats"][-1]["end_second"] = 38
    agent.run = AsyncMock(return_value=package)

    from app.core import logging as logging_module
    original_broadcast = logging_module.log_manager.broadcast
    logging_module.log_manager.broadcast = AsyncMock()
    try:
        with pytest.raises(ValueError, match="do not cover the target duration"):
            await agent.generate_script(research_data={}, target_duration=40)
    finally:
        logging_module.log_manager.broadcast = original_broadcast
