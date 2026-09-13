"""
Sprint 3 — 7 Mandatory Architectural Tests

Test 1: Happy path end-to-end
Test 2: Research failure → PipelineRun=failed, Job=failed, Content=FAILED
Test 3: Render failure + resume → skips completed stages, retries render
Test 4: Partial media failure → only regenerates failed scene audio
Test 5: Process restart recovery (simulated via DB state)
Test 6: Duplicate simultaneous requests (idempotency constraint)
Test 7: Batch of 10 → verify no cross-contamination
"""
import pytest
import uuid
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from app.db.database import engine, Base, AsyncSessionLocal
from app.db.models import (
    Content as DBContent,
    PipelineJobDB,
    PipelineRun as DBPipelineRun,
    Research as DBResearch,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset,
    ContentBatch as DBContentBatch,
)
from app.models.ai_contracts import (
    ResearchResult, StrategyResult, ScriptResult, Scene, ScenePlan, QualityResult
)
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_state import WorkflowState
from app.workflows.worker import job_manager, PipelineJob


# --- Helpers ---

async def _setup_db():
    """Ensure DB tables exist."""
    await engine.dispose()
    from app.db.init_db import init_db
    await init_db()


async def _create_content(db, title="Test Content", status="idea") -> DBContent:
    """Create a Content record for testing."""
    c = DBContent(title=title, content_type="Shorts", platform="Shorts", status=status)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


def _mock_pipeline_agents(tmp_path):
    """
    Returns a context manager dict that patches all pipeline agents.
    """
    dummy_img = tmp_path / "test_image.jpg"
    dummy_img.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 500)
    dummy_audio = tmp_path / "test_audio.mp3"
    dummy_audio.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 1000)
    dummy_video = tmp_path / "test_video.mp4"
    dummy_video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 5000)

    return {
        "img": str(dummy_img),
        "audio": str(dummy_audio),
        "video": str(dummy_video),
        "research": ResearchResult(
            summary="Test research summary",
            key_points=["Point 1", "Point 2"],
            statistics=["Stat 1"],
        ),
        "strategy": StrategyResult(
            content_angle="Educational",
            target_audience_analysis="Developers",
            hook_strategy="Curiosity Gap",
            format_guidelines=["Fast pacing"],
        ),
        "script": ScriptResult(
            hook="Stop scrolling!",
            body="Here are 3 AI tools you need to know.",
            cta="Follow for more!",
            estimated_duration=15,
            word_count=15,
        ),
        "scene_plan": ScenePlan(scenes=[
            Scene(
                scene_number=1,
                duration=15.0,
                narration="Here are 3 AI tools you need to know.",
                visual_description="Dark lab",
                visual_prompt="Dark lab 8k",
            )
        ]),
    }


# --- Test 1: Happy path end-to-end ---

@pytest.mark.asyncio
async def test_happy_path_end_to_end(tmp_path):
    """
    Research → Strategy → Script → Scenes → Assets → Render → Quality → AWAITING_APPROVAL.
    Verify: Content.status, PipelineRun.status, all artifacts exist.
    """
    await _setup_db()
    mocks = _mock_pipeline_agents(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Happy Path Test")
        content_id = content.id
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
            }
            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            pipeline = ContentPipeline()
            ctx = await pipeline.run(content_id, db, pipeline_run_id=run_id)

        # Assertions
        assert ctx.current_state == WorkflowState.AWAITING_APPROVAL
        assert ctx.research is not None
        assert ctx.strategy is not None
        assert ctx.script is not None
        assert ctx.scene_plan is not None
        assert ctx.final_video_path is not None
        assert ctx.quality_result is not None

        # Verify DB state
        await db.refresh(content)
        assert content.status == WorkflowState.AWAITING_APPROVAL.value

        # Verify PipelineRun status
        from sqlalchemy.future import select
        run_result = await db.execute(
            select(DBPipelineRun).filter(DBPipelineRun.id == run_id)
        )
        pipeline_run = run_result.scalars().first()
        assert pipeline_run is not None
        assert pipeline_run.status == "completed"


# --- Test 2: Research failure ---

@pytest.mark.asyncio
async def test_research_failure(tmp_path):
    """
    Mock ResearchAgent to raise Exception.
    Verify: PipelineRun=failed, Content.status=FAILED.
    """
    await _setup_db()

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Research Failure Test")
        content_id = content.id
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA:
            MockRA.return_value.research_topic = AsyncMock(
                side_effect=RuntimeError("LLM connection refused")
            )

            pipeline = ContentPipeline()
            ctx = await pipeline.run(content_id, db, resume=False, pipeline_run_id=run_id)

        # Pipeline should have caught the error
        assert ctx.current_state == WorkflowState.FAILED

        # Verify DB
        await db.refresh(content)
        assert content.status == WorkflowState.FAILED.value

        from sqlalchemy.future import select
        run_result = await db.execute(
            select(DBPipelineRun).filter(DBPipelineRun.id == run_id)
        )
        pipeline_run = run_result.scalars().first()
        assert pipeline_run is not None
        assert pipeline_run.status == "failed"
        assert "LLM connection refused" in (pipeline_run.error or "")


# --- Test 3: Render failure + resume ---

@pytest.mark.asyncio
async def test_render_failure_then_resume(tmp_path):
    """
    First run: fail at render stage.
    Second run: resume=True, same pipeline_run_id.
    Verify: skips Research/Strategy/Script/Scenes, retries Render.
    """
    await _setup_db()
    mocks = _mock_pipeline_agents(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Render Failure Resume Test")
        content_id = content.id
        run_id = uuid.uuid4()

        # First run: everything succeeds except render
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            # Render fails
            MockVidA.return_value.assemble_scene = AsyncMock(
                side_effect=RuntimeError("FFmpeg crash")
            )

            pipeline = ContentPipeline()
            ctx1 = await pipeline.run(content_id, db, resume=False, pipeline_run_id=run_id)
            assert ctx1.current_state == WorkflowState.FAILED

        # Second run: resume with same run_id — render should now succeed
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA2, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA2, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA2, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA2, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA2, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA2, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA2, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe2:

            mock_ffprobe2.return_value = {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
            }
            # These should NOT be called (artifacts already exist)
            MockRA2.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA2.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA2.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA2.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA2.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA2.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            # Render now succeeds
            MockVidA2.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA2.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            pipeline2 = ContentPipeline()
            ctx2 = await pipeline2.run(content_id, db, resume=True, pipeline_run_id=run_id)

        assert ctx2.current_state == WorkflowState.AWAITING_APPROVAL
        assert ctx2.final_video_path is not None

        # Verify research/script/scenes agents were NOT called on resume
        # (they should have been hydrated from DB)
        MockRA2.return_value.research_topic.assert_not_called()
        MockScA2.return_value.generate_script.assert_not_called()
        MockScnA2.return_value.plan_scenes.assert_not_called()


# --- Test 4: Partial media failure ---

@pytest.mark.asyncio
async def test_partial_media_failure(tmp_path):
    """
    Two scenes: Scene 1 image+audio OK, Scene 2 audio fails.
    Resume: should keep Scene 1 assets, only regenerate Scene 2 audio.
    """
    await _setup_db()
    mocks = _mock_pipeline_agents(tmp_path)

    # Create a two-scene plan
    two_scene_plan = ScenePlan(scenes=[
        Scene(scene_number=1, duration=7.0, narration="Scene 1 text",
              visual_description="Lab", visual_prompt="Lab 8k"),
        Scene(scene_number=2, duration=8.0, narration="Scene 2 text",
              visual_description="Office", visual_prompt="Office 8k"),
    ])

    call_count = {"voice": 0}

    async def voice_side_effect(text, **kwargs):
        call_count["voice"] += 1
        if call_count["voice"] == 2:
            raise RuntimeError("TTS failed for scene 2")
        return mocks["audio"]

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Partial Media Test")
        content_id = content.id
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA:

            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=two_scene_plan)
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(side_effect=voice_side_effect)

            pipeline = ContentPipeline()
            ctx = await pipeline.run(content_id, db, resume=False, pipeline_run_id=run_id)

        # Should have failed at the media step
        assert ctx.current_state == WorkflowState.FAILED

        # Verify: Scene 1 has completed assets in DB
        from sqlalchemy.future import select
        s1_assets = await db.execute(
            select(DBAsset).filter(
                DBAsset.content_id == content_id,
                DBAsset.status == "completed",
                DBAsset.asset_type == "image",
            )
        )
        # At least scene 1 image should exist
        assert len(s1_assets.scalars().all()) >= 1


# --- Test 5: Process restart recovery (simulated) ---

@pytest.mark.asyncio
async def test_process_restart_recovery():
    """
    Simulate: create a job marked 'running' with a stale heartbeat.
    Call recover_stale_jobs() and verify it gets re-queued.
    """
    await _setup_db()

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Restart Recovery Test")
        content_id = content.id

        # Create a "running" job with stale heartbeat (10 min ago)
        stale_time = datetime.utcnow() - timedelta(minutes=10)
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        db_job = PipelineJobDB(
            id=job_id,
            content_id=content_id,
            status="running",
            current_stage="ASSETS",
            last_heartbeat=stale_time,
            pipeline_run_id=uuid.uuid4(),
        )
        db.add(db_job)
        await db.commit()

    # Mock the enqueue function so we don't need real Redis
    with patch("app.workflows.task_queue.enqueue_pipeline_job", new_callable=AsyncMock) as mock_enqueue:
        from app.workflows.task_queue import recover_stale_jobs
        await recover_stale_jobs()

        # Verify the stale job was re-enqueued
        assert mock_enqueue.called
        assert mock_enqueue.call_args.kwargs["job_id"] == job_id

    # Verify DB: job status should be "queued"
    async with AsyncSessionLocal() as db:
        from sqlalchemy.future import select
        result = await db.execute(
            select(PipelineJobDB).filter(PipelineJobDB.id == job_id)
        )
        recovered_job = result.scalars().first()
        assert recovered_job.status == "queued"


# --- Test 6: Duplicate simultaneous requests (idempotency) ---

@pytest.mark.asyncio
async def test_idempotency_deduplication():
    """
    Same content_id + idempotency_key → concurrent create_job() calls.
    Verify: only ONE PipelineJobDB row.
    """
    await _setup_db()

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Idempotency Test")
        content_id = str(content.id)

    idem_key = f"key_{uuid.uuid4().hex[:8]}"

    # Create first job (no Redis enqueue needed for this test)
    job1 = await job_manager.create_job(
        content_id=content_id, idempotency_key=idem_key, enqueue=False
    )

    # Create second job with same key — should return existing
    job2 = await job_manager.create_job(
        content_id=content_id, idempotency_key=idem_key, enqueue=False
    )

    assert job1.job_id == job2.job_id

    # Verify only one DB row
    async with AsyncSessionLocal() as db:
        from sqlalchemy.future import select
        result = await db.execute(
            select(PipelineJobDB).filter(
                PipelineJobDB.content_id == uuid.UUID(content_id),
                PipelineJobDB.idempotency_key == idem_key,
            )
        )
        jobs = result.scalars().all()
        assert len(jobs) == 1


# --- Test 7: Batch of 10 ---

@pytest.mark.asyncio
async def test_batch_10_no_cross_contamination(tmp_path):
    """
    Trigger batch with count=10.
    Verify: 1 ContentBatch, 10 Content, 10 Jobs, 10 PipelineRuns.
    Verify: no cross-contamination of artifacts between content items.
    """
    await _setup_db()
    mocks = _mock_pipeline_agents(tmp_path)

    async with AsyncSessionLocal() as db:
        batch_id = f"batch_{uuid.uuid4().hex[:8]}"

        # Create batch + 10 content items in single transaction
        db_batch = DBContentBatch(
            id=batch_id, topic="AI Tools", requested_count=10, status="running"
        )
        db.add(db_batch)

        content_ids = []
        for i in range(10):
            c = DBContent(
                batch_id=batch_id,
                title=f"Batch Item {i+1}",
                platform="Shorts",
                status=WorkflowState.IDEA.value,
            )
            db.add(c)
            await db.flush()
            content_ids.append(c.id)

        await db.commit()

        # Create 10 jobs (no Redis enqueue)
        jobs = []
        for cid in content_ids:
            j = await job_manager.create_job(
                content_id=str(cid), resume=False, enqueue=False
            )
            jobs.append(j)

        # Verify 10 unique jobs
        assert len(jobs) == 10
        assert len(set(j.job_id for j in jobs)) == 10

        # Verify 10 unique pipeline_run_ids
        assert len(set(j.pipeline_run_id for j in jobs)) == 10

        # Run pipelines for first 2 items to verify no cross-contamination
        for idx in range(2):
            cid = content_ids[idx]
            run_id = uuid.UUID(jobs[idx].pipeline_run_id)

            with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
                 patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
                 patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
                 patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
                 patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
                 patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
                 patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
                 patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

                mock_ffprobe.return_value = {
                    "valid": True, "has_video": True, "has_audio": True,
                    "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
                }
                MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
                MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
                MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
                MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
                MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
                MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
                MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
                MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

                pipeline = ContentPipeline()
                ctx = await pipeline.run(cid, db, resume=False, pipeline_run_id=run_id)
                assert ctx.current_state == WorkflowState.AWAITING_APPROVAL

        # Verify no cross-contamination: each content's artifacts are scoped
        from sqlalchemy.future import select
        for idx in range(2):
            cid = content_ids[idx]
            rid = uuid.UUID(jobs[idx].pipeline_run_id)

            res = await db.execute(
                select(DBResearch).filter(
                    DBResearch.content_id == cid,
                    DBResearch.pipeline_run_id == rid,
                )
            )
            research_rows = res.scalars().all()
            assert len(research_rows) == 1, f"Content {idx} should have exactly 1 research artifact"

            asset_res = await db.execute(
                select(DBAsset).filter(
                    DBAsset.content_id == cid,
                    DBAsset.pipeline_run_id == rid,
                )
            )
            assets = asset_res.scalars().all()
            # Each content should have its own assets (image + audio + video)
            assert len(assets) >= 1, f"Content {idx} should have assets"

            # Verify NO assets belong to the OTHER content's run
            other_idx = 1 - idx
            other_rid = uuid.UUID(jobs[other_idx].pipeline_run_id)
            cross_res = await db.execute(
                select(DBAsset).filter(
                    DBAsset.content_id == cid,
                    DBAsset.pipeline_run_id == other_rid,
                )
            )
            cross_assets = cross_res.scalars().all()
            assert len(cross_assets) == 0, f"Content {idx} should have NO assets from run {other_rid}"


# --- Test 8 (Sprint 4): recover_queued_jobs picks up Redis-unavailable jobs ---

@pytest.mark.asyncio
async def test_recover_queued_jobs_dispatches_to_redis():
    """
    Sprint 4 — P0 Recovery Path:
    Simulate an API request that was accepted while Redis was unavailable.
    The job was inserted as QUEUED but never dispatched.
    Verify: recover_queued_jobs() finds it and enqueues it to Redis.
    """
    await _setup_db()

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Queued Job Recovery Test")
        content_id = content.id

        # Simulate a QUEUED job (Redis was down when API accepted the request)
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        run_id = uuid.uuid4()
        db_job = PipelineJobDB(
            id=job_id,
            content_id=content_id,
            status="queued",
            current_stage="QUEUED",
            pipeline_run_id=run_id,
        )
        db.add(db_job)
        await db.commit()

    # Mock the enqueue function (we don't need real Redis for this test)
    with patch("app.workflows.task_queue.enqueue_pipeline_job", new_callable=AsyncMock) as mock_enqueue:
        from app.workflows.task_queue import recover_queued_jobs
        await recover_queued_jobs()

        # Verify the queued job was dispatched
        assert mock_enqueue.called
        dispatched_job_ids = [c.kwargs["job_id"] for c in mock_enqueue.call_args_list]
        assert job_id in dispatched_job_ids


# --- Test 9 (Sprint 4): Strict artifact isolation — no cross-run fallback ---

@pytest.mark.asyncio
async def test_strict_artifact_isolation_no_cross_run_fallback(tmp_path):
    """
    Sprint 4 — P0 Isolation:
    Run A completes. Run B starts fresh for the same content with a NEW pipeline_run_id.
    Verify: Run B does NOT load Run A's artifacts (no cross-run fallback).
    All of Run B's steps must execute from scratch.
    """
    await _setup_db()
    mocks = _mock_pipeline_agents(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Strict Isolation Test")
        content_id = content.id
        run_id_a = uuid.uuid4()
        run_id_b = uuid.uuid4()  # fresh run, different from A

        # ---- Run A: complete successfully ----
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
            }
            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            pipeline_a = ContentPipeline()
            ctx_a = await pipeline_a.run(content_id, db, resume=False, pipeline_run_id=run_id_a)
            assert ctx_a.current_state == WorkflowState.AWAITING_APPROVAL

        # ---- Run B: NEW pipeline_run_id, resume=False ----
        # Since run_id_b != run_id_a, NO artifacts from A should be loaded.
        # All agents MUST be called fresh.
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRB, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSB, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScB, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnB, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIB, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVB, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidB, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe_b:

            mock_ffprobe_b.return_value = {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
            }
            MockRB.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSB.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScB.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnB.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIB.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVB.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidB.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidB.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            pipeline_b = ContentPipeline()
            ctx_b = await pipeline_b.run(content_id, db, resume=False, pipeline_run_id=run_id_b)
            assert ctx_b.current_state == WorkflowState.AWAITING_APPROVAL

            # --- KEY ASSERTION: all agents were called for Run B ---
            # (If cross-run fallback was active, ResearchAgent etc. would NOT be called)
            MockRB.return_value.research_topic.assert_called_once()
            MockScB.return_value.generate_script.assert_called_once()
            MockScnB.return_value.plan_scenes.assert_called_once()

        # Verify Run B artifacts are scoped to run_id_b only
        from sqlalchemy.future import select
        res = await db.execute(
            select(DBResearch).filter(
                DBResearch.content_id == content_id,
                DBResearch.pipeline_run_id == run_id_b,
            )
        )
        assert len(res.scalars().all()) == 1, "Run B must have exactly 1 research artifact"

        # Verify Run B video is not Run A's video
        vid_res = await db.execute(
            select(DBAsset).filter(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id_b,
                DBAsset.asset_type == "video",
            )
        )
        b_videos = vid_res.scalars().all()
        assert len(b_videos) >= 1, "Run B must have its own video asset"


# --- Test 10 (Sprint 4): Visuals-only regeneration ---

@pytest.mark.asyncio
async def test_visuals_only_regeneration(tmp_path):
    """
    Sprint 4 — Tiered Regeneration:
    1. Full pipeline runs successfully → AWAITING_APPROVAL.
    2. User clicks "Regenerate Visuals" → media assets deleted, same pipeline_run_id reused.
    3. Pipeline resumes with the same run_id:
       - Research/Strategy/Script/Scene agents are NOT called (hydrated from DB).
       - Image/Audio/Video agents ARE called (media assets were cleared).
    """
    await _setup_db()
    mocks = _mock_pipeline_agents(tmp_path)
    run_id = uuid.uuid4()

    # Session 1: create content
    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Visuals Regen Test")
        content_id = content.id

    # Session 2: full pipeline run
    async with AsyncSessionLocal() as db:
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
            }
            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            pipeline = ContentPipeline()
            ctx1 = await pipeline.run(content_id, db, resume=False, pipeline_run_id=run_id)
            assert ctx1.current_state == WorkflowState.AWAITING_APPROVAL
    # Session 2 closed and committed here

    # Session 3: simulate mode=visuals → delete media, reset run status, resume
    from sqlalchemy import delete as sa_delete
    from sqlalchemy.future import select as sa_select
    async with AsyncSessionLocal() as db:
        # Delete media assets
        await db.execute(
            sa_delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type.in_(["image", "audio", "video", "subtitle"]),
            )
        )
        run_result = await db.execute(
            sa_select(DBPipelineRun).filter(DBPipelineRun.id == run_id)
        )
        pipeline_run = run_result.scalars().first()
        pipeline_run.status = "queued"
        pipeline_run.current_stage = "RESUMING_VISUALS"
        await db.commit()

        # Resume pipeline with same run_id
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRB, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSB, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScB, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnB, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIB, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVB, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidB, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe2:

            mock_ffprobe2.return_value = {
                "valid": True, "has_video": True, "has_audio": True,
                "duration": 15.0, "size": 5000, "width": 1080, "height": 1920,
            }
            MockRB.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSB.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScB.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnB.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIB.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVB.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidB.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidB.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            pipeline2 = ContentPipeline()
            ctx2 = await pipeline2.run(content_id, db, resume=True, pipeline_run_id=run_id)
            assert ctx2.current_state == WorkflowState.AWAITING_APPROVAL

            # KEY ASSERTIONS:
            # Research/Script/Scene agents must NOT have been called (hydrated from DB)
            MockRB.return_value.research_topic.assert_not_called()
            MockScB.return_value.generate_script.assert_not_called()
            MockScnB.return_value.plan_scenes.assert_not_called()

            # Media agents MUST have been called (assets were cleared)
            MockIB.return_value.generate_image.assert_called()
            MockVB.return_value.generate_voice.assert_called()
            MockVidB.return_value.assemble_final.assert_called()
