import pytest
import uuid
import os
from unittest.mock import AsyncMock, patch
import pytest_asyncio
from app.models.ai_contracts import (
    ResearchResult, StrategyResult, ScriptResult, Scene, ScenePlan, QualityResult, validate_ai_response
)
from app.workflows.workflow_state import WorkflowState, can_transition
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_context import WorkflowContext
from app.quality.evaluator import QualityAgent
from app.db.database import engine, Base, AsyncSessionLocal
from app.db.models import Content as DBContent

def test_ai_contracts_validation():
    # Valid Research parsing
    raw_research = {
        "summary": "AI tools in 2026",
        "key_points": ["Point 1", "Point 2"],
        "statistics": ["100x growth"]
    }
    res = validate_ai_response(raw_research, ResearchResult)
    assert isinstance(res, ResearchResult)
    assert res.summary == "AI tools in 2026"
    assert len(res.key_points) == 2

    # Script post-init word count calculation
    raw_script = {
        "hook": "Stop scrolling!",
        "body": "Here are 3 secret AI tools you need to know today.",
        "cta": "Follow for more AI tips!",
        "estimated_duration": 30
    }
    script = validate_ai_response(raw_script, ScriptResult)
    assert script.word_count > 0

    # Scene Plan validation
    raw_scenes = {
        "scenes": [
            {
                "scene_number": 1,
                "duration": 4.0,
                "narration": "Intro scene narration",
                "visual_description": "A dark tech laboratory",
                "visual_prompt": "Dark high tech laboratory 8k"
            }
        ]
    }
    plan = validate_ai_response(raw_scenes, ScenePlan)
    assert len(plan.scenes) == 1
    assert plan.scenes[0].duration == 4.0

def test_workflow_state_transitions():
    assert can_transition(WorkflowState.IDEA, WorkflowState.RESEARCH)
    assert can_transition(WorkflowState.RESEARCH, WorkflowState.SCRIPT)
    assert can_transition(WorkflowState.SCRIPT, WorkflowState.SCENES)
    assert can_transition(WorkflowState.SCENES, WorkflowState.ASSETS)
    assert can_transition(WorkflowState.ASSETS, WorkflowState.RENDER)
    assert can_transition(WorkflowState.RENDER, WorkflowState.QUALITY_CHECK)
    assert can_transition(WorkflowState.QUALITY_CHECK, WorkflowState.AWAITING_APPROVAL)
    assert can_transition(WorkflowState.AWAITING_APPROVAL, WorkflowState.APPROVED)
    
    # Retry from FAILED state
    assert can_transition(WorkflowState.FAILED, WorkflowState.RESEARCH)

@pytest.mark.asyncio
async def test_quality_agent_scoring():
    agent = QualityAgent()
    script = ScriptResult(
        hook="Attention developers!",
        body="This is an awesome script explaining autonomous pipelines.",
        cta="Subscribe now!",
        estimated_duration=30,
        word_count=25
    )
    plan = ScenePlan(scenes=[
        Scene(scene_number=1, duration=5.0, narration="Scene 1", visual_description="Lab", visual_prompt="Lab prompt")
    ])
    
    res = await agent.evaluate(script=script, scene_plan=plan)
    assert isinstance(res, QualityResult)
    assert res.overall_score >= 0.0

@pytest.mark.asyncio
async def test_full_pipeline_orchestration(tmp_path):
    await engine.dispose()
    from app.db.init_db import init_db
    await init_db()

    dummy_img = tmp_path / "test_image.jpg"
    dummy_img.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF")
    
    dummy_audio = tmp_path / "test_audio.mp3"
    dummy_audio.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 1000)

    dummy_video = tmp_path / "test_video.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 5000)

    async with AsyncSessionLocal() as db:
        db_content = DBContent(
            title="The Future of Autonomous AI Factories",
            content_type="Shorts",
            platform="Shorts",
            status="idea"
        )
        db.add(db_content)
        await db.commit()
        await db.refresh(db_content)
        content_id = db_content.id

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockResearchAgent, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockStrategyAgent, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScriptAgent, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockSceneAgent, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockImageAgent, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVoiceAgent, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVideoAgent, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:
            
            mock_ffprobe.return_value = {
                "valid": True,
                "has_video": True,
                "has_audio": True,
                "duration": 15.0,
                "size": 5000,
                "width": 1080,
                "height": 1920
            }

            mock_research_inst = MockResearchAgent.return_value
            mock_research_inst.research_topic = AsyncMock(return_value=ResearchResult(
                summary="AI tools summary",
                key_points=["Point 1", "Point 2"],
                statistics=["100x growth"]
            ))

            mock_strategy_inst = MockStrategyAgent.return_value
            mock_strategy_inst.develop_strategy = AsyncMock(return_value=StrategyResult(
                content_angle="Educational",
                target_audience_analysis="Tech Enthusiasts",
                hook_strategy="Curiosity Gap",
                format_guidelines=["Fast pacing"]
            ))

            mock_script_inst = MockScriptAgent.return_value
            mock_script_inst.generate_script = AsyncMock(return_value=ScriptResult(
                hook="Stop scrolling!",
                body="Here are 3 secret AI tools you need to know today.",
                cta="Follow for more AI tips!",
                estimated_duration=15.0,
                word_count=20
            ))

            mock_scene_inst = MockSceneAgent.return_value
            mock_scene_inst.plan_scenes = AsyncMock(return_value=ScenePlan(scenes=[
                Scene(
                    scene_number=1,
                    duration=15.0,
                    narration="Here are 3 secret AI tools you need to know today.",
                    visual_description="Dark high tech laboratory",
                    visual_prompt="Dark high tech laboratory 8k"
                )
            ]))

            mock_img_inst = MockImageAgent.return_value
            mock_img_inst.generate_image = AsyncMock(return_value=str(dummy_img))
            
            mock_voice_inst = MockVoiceAgent.return_value
            mock_voice_inst.generate_voice = AsyncMock(return_value=str(dummy_audio))

            mock_vid_inst = MockVideoAgent.return_value
            mock_vid_inst.assemble_scene = AsyncMock(return_value=str(dummy_video))
            mock_vid_inst.assemble_final = AsyncMock(return_value=str(dummy_video))

            pipeline = ContentPipeline()
            ctx = await pipeline.run(content_id, db)

            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL
            assert ctx.research is not None
            assert ctx.strategy is not None
            assert ctx.script is not None
            assert ctx.scene_plan is not None
            assert ctx.final_video_path is not None
            assert ctx.quality_result is not None
            assert ctx.quality_result.passed is True

@pytest.mark.asyncio
async def test_strict_workflow_transitions():
    from app.workflows.workflow_state import update_workflow_state, InvalidWorkflowTransitionError
    await engine.dispose()
    
    async with AsyncSessionLocal() as db:
        content = DBContent(title="Strict Transition Test", status="idea")
        db.add(content)
        await db.commit()
        await db.refresh(content)

        # Illegal jump: IDEA -> PUBLISHED should fail
        with pytest.raises(InvalidWorkflowTransitionError):
            await update_workflow_state(db, content.id, WorkflowState.PUBLISHED, force=False)

        # Forced transition should succeed
        await update_workflow_state(db, content.id, WorkflowState.PUBLISHED, force=True)
        await db.refresh(content)
        assert content.status == WorkflowState.PUBLISHED.value

@pytest.mark.asyncio
async def test_resume_context_hydration(tmp_path):
    from app.db.models import Research as DBResearch, Script as DBScript, Scene as DBScene
    await engine.dispose()
    
    async with AsyncSessionLocal() as db:
        content = DBContent(title="Hydration Test Topic", status="idea")
        db.add(content)
        await db.commit()
        await db.refresh(content)
        
        db_research = DBResearch(content_id=content.id, summary="Hydrated research summary", key_points=["point1"], status="completed")
        db_script = DBScript(content_id=content.id, hook="Hydrated hook", body="Hydrated body text", cta="Subscribe", estimated_duration=25, status="completed")
        db_scene = DBScene(content_id=content.id, scene_number=1, duration=5.0, narration="Scene 1", status="completed")
        
        db.add(db_research)
        db.add(db_script)
        db.add(db_scene)
        await db.commit()

        pipeline = ContentPipeline()
        ctx = WorkflowContext(content_id=content.id)
        await pipeline.hydrate_context(ctx, db)

        assert ctx.research is not None
        assert ctx.research.summary == "Hydrated research summary"
        assert ctx.script is not None
        assert ctx.script.hook == "Hydrated hook"
        assert ctx.scene_plan is not None
        assert len(ctx.scene_plan.scenes) == 1

@pytest.mark.asyncio
async def test_idempotency_deduplication():
    from app.workflows.worker import job_manager
    await engine.dispose()
    
    async with AsyncSessionLocal() as db:
        content = DBContent(title="Idempotency Test Topic", status="idea")
        db.add(content)
        await db.commit()
        await db.refresh(content)
        content_id = str(content.id)

    key = f"key_{uuid.uuid4().hex[:6]}"
    job1 = await job_manager.create_job(content_id=content_id, idempotency_key=key)
    job2 = await job_manager.create_job(content_id=content_id, idempotency_key=key)

    assert job1.job_id == job2.job_id

@pytest.mark.asyncio
async def test_batch_strategy_agent():
    from app.agents.batch_strategy import BatchStrategyAgent
    agent = BatchStrategyAgent()
    plan = await agent.generate_batch_plan(topic="Autonomous AI Agents", count=3)

    assert plan.topic == "Autonomous AI Agents"
    assert len(plan.variations) >= 1
    assert plan.variations[0].title is not None
    assert plan.variations[0].angle is not None
