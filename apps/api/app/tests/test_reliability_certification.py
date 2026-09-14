"""ConGenAI Reliability Certification v1 Suite.

Certifies all 20 production failure, recovery, isolation, and robustness scenarios:
 1. One complete video (happy path end-to-end)
 2. Research failure → resume
 3. LLM failure → resume
 4. Image failure → retry/resume
 5. TTS failure → retry/resume
 6. FFmpeg failure → resume
 7. QA failure gating (low score fails transition)
 8. Worker restart (stale heartbeat recovery)
 9. Redis restart (queued job recovery)
10. API restart (in-flight state persistence)
11. Duplicate requests (DB partial unique index guard)
12. Concurrent regeneration guard (409 Conflict)
13. Scene-level regeneration isolation
14. Full regeneration lineage tracking
15. 10-video batch orchestration
16. 10 videos strict artifact isolation
17. No external image provider (100% offline privacy)
18. Missing ffprobe fail-closed QA
19. Invalid evidence / factual integrity (no fabricated claims)
20. Failed job correctly transitions to status="failed"
"""

import pytest
import os
import uuid
import tempfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from PIL import Image

from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.database import AsyncSessionLocal, engine
from app.db.init_db import init_db
from app.db.models import (
    Content as DBContent,
    ContentIdea as DBContentIdea,
    ContentBatch as DBContentBatch,
    PipelineRun as DBPipelineRun,
    Asset as DBAsset,
    Scene as DBScene,
    Research as DBResearch,
    Strategy as DBStrategy,
    Script as DBScript,
    PipelineJobDB,
)
from app.core.config import settings
from app.models.ai_contracts import (
    ResearchResult, StrategyResult, ScriptResult, Scene, ScenePlan, QualityResult
)
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_state import WorkflowState
from app.workflows.worker import job_manager, PipelineJob
from app.workflows.task_queue import execute_pipeline_job, recover_stale_jobs, recover_queued_jobs
from app.api.v1.pipeline_regeneration import regenerate_content, RegenerateBody
from app.api.v1.pipeline_batch import trigger_batch_pipeline, BatchPipelineRequest
from app.agents.batch_strategy import BatchStrategyResult, BatchVariation
from app.services.image_service import ImageService
from app.services.thumbnail_generator import ThumbnailGeneratorService, ThumbnailStyle
from app.services.broll_service import BRollService
from app.quality.evaluator import QualityAgent


# --- Fixtures and Mocks ---

@pytest.fixture(autouse=True)
def ensure_privacy():
    old = getattr(settings, "ALLOW_EXTERNAL_GENERATION", False)
    settings.ALLOW_EXTERNAL_GENERATION = False
    yield
    settings.ALLOW_EXTERNAL_GENERATION = old


async def _setup_db():
    await engine.dispose()
    await init_db()


async def _create_content(db, title="Cert Content", status="idea") -> DBContent:
    c = DBContent(title=title, content_type="Shorts", platform="Shorts", status=status)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


def _mock_assets(tmp_path):
    dummy_img = tmp_path / "cert_img.jpg"
    dummy_img.write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 500)
    dummy_aud = tmp_path / "cert_aud.mp3"
    dummy_aud.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 1000)
    dummy_vid = tmp_path / "cert_vid.mp4"
    dummy_vid.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 5000)

    return {
        "img": str(dummy_img),
        "audio": str(dummy_aud),
        "video": str(dummy_vid),
        "research": ResearchResult(
            summary="Reliability Research",
            key_points=["Scalability", "Fault-Tolerance"],
            statistics=["99.99% Uptime SLA"],
        ),
        "strategy": StrategyResult(
            content_angle="Technical Deep-Dive",
            target_audience_analysis="Engineers",
            hook_strategy="Statistical Shock",
            format_guidelines=["High information density"],
        ),
        "script": ScriptResult(
            hook="Your backend is secretly failing.",
            body="Here is how to make your async pipeline 100% resilient.",
            cta="Subscribe for more architecture breakdowns.",
            estimated_duration=15,
            word_count=18,
        ),
        "scene_plan": ScenePlan(scenes=[
            Scene(
                scene_number=1,
                duration=15.0,
                narration="Here is how to make your async pipeline 100% resilient.",
                visual_description="Cyber terminal code flow",
                visual_prompt="Terminal with neon glowing python code 8k",
            )
        ]),
    }


# ==========================================
# 1. Complete Video Happy Path
# ==========================================
@pytest.mark.asyncio
async def test_01_complete_video_happy_path(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 01 Happy Path")
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
            ctx = await pipeline.run(content.id, db, pipeline_run_id=run_id)
            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL

        await db.refresh(content)
        assert content.status == WorkflowState.AWAITING_APPROVAL.value


# ==========================================
# 2. Research Failure -> Resume
# ==========================================
@pytest.mark.asyncio
async def test_02_research_failure_then_resume(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 02 Research Fail")
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA:
            MockRA.return_value.research_topic = AsyncMock(side_effect=RuntimeError("Research API timeout"))
            pipeline = ContentPipeline()
            with pytest.raises(RuntimeError):
                await pipeline.run(content.id, db, resume=False, pipeline_run_id=run_id)

        # Resume run
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {"valid": True, "has_video": True, "has_audio": True, "duration": 15.0, "size": 5000, "width": 1080, "height": 1920}
            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            ctx = await pipeline.run(content.id, db, resume=True, pipeline_run_id=run_id)
            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL


# ==========================================
# 3. LLM Failure -> Resume
# ==========================================
@pytest.mark.asyncio
async def test_03_llm_failure_then_resume(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 03 LLM Fail")
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA:

            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(side_effect=RuntimeError("Ollama connection reset"))

            pipeline = ContentPipeline()
            with pytest.raises(RuntimeError):
                await pipeline.run(content.id, db, resume=False, pipeline_run_id=run_id)

        # Resume after LLM recovers
        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {"valid": True, "has_video": True, "has_audio": True, "duration": 15.0, "size": 5000, "width": 1080, "height": 1920}
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            ctx = await pipeline.run(content.id, db, resume=True, pipeline_run_id=run_id)
            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL


# ==========================================
# 4. Image Failure -> Retry/Resume
# ==========================================
@pytest.mark.asyncio
async def test_04_image_failure_retry_resume(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 04 Image Fail")
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA:

            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(side_effect=RuntimeError("ComfyUI VRAM Out of Memory"))
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])

            pipeline = ContentPipeline()
            with pytest.raises(RuntimeError):
                await pipeline.run(content.id, db, resume=False, pipeline_run_id=run_id)

        # Resume: image generation now succeeds
        with patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {"valid": True, "has_video": True, "has_audio": True, "duration": 15.0, "size": 5000, "width": 1080, "height": 1920}
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            ctx = await pipeline.run(content.id, db, resume=True, pipeline_run_id=run_id)
            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL


# ==========================================
# 5. TTS Failure -> Retry/Resume
# ==========================================
@pytest.mark.asyncio
async def test_05_tts_failure_retry_resume(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 05 TTS Fail")
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA:

            MockRA.return_value.research_topic = AsyncMock(return_value=mocks["research"])
            MockSA.return_value.develop_strategy = AsyncMock(return_value=mocks["strategy"])
            MockScA.return_value.generate_script = AsyncMock(return_value=mocks["script"])
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(side_effect=RuntimeError("TTS engine crash"))

            pipeline = ContentPipeline()
            with pytest.raises(RuntimeError):
                await pipeline.run(content.id, db, resume=False, pipeline_run_id=run_id)

        # Resume: TTS recovers
        with patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {"valid": True, "has_video": True, "has_audio": True, "duration": 15.0, "size": 5000, "width": 1080, "height": 1920}
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            ctx = await pipeline.run(content.id, db, resume=True, pipeline_run_id=run_id)
            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL


# ==========================================
# 6. FFmpeg Failure -> Resume
# ==========================================
@pytest.mark.asyncio
async def test_06_ffmpeg_failure_then_resume(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 06 FFmpeg Fail")
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
            MockScnA.return_value.plan_scenes = AsyncMock(return_value=mocks["scene_plan"])
            MockIA.return_value.generate_image = AsyncMock(return_value=mocks["img"])
            MockVA.return_value.generate_voice = AsyncMock(return_value=mocks["audio"])
            MockVidA.return_value.assemble_scene = AsyncMock(side_effect=RuntimeError("FFmpeg segfault"))

            pipeline = ContentPipeline()
            with pytest.raises(RuntimeError):
                await pipeline.run(content.id, db, resume=False, pipeline_run_id=run_id)

        # Resume: FFmpeg succeeds
        with patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            mock_ffprobe.return_value = {"valid": True, "has_video": True, "has_audio": True, "duration": 15.0, "size": 5000, "width": 1080, "height": 1920}
            MockVidA.return_value.assemble_scene = AsyncMock(return_value=mocks["video"])
            MockVidA.return_value.assemble_final = AsyncMock(return_value=mocks["video"])

            ctx = await pipeline.run(content.id, db, resume=True, pipeline_run_id=run_id)
            assert ctx.current_state == WorkflowState.AWAITING_APPROVAL


# ==========================================
# 7. QA Failure Gating
# ==========================================
@pytest.mark.asyncio
async def test_07_qa_failure_gating(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)

    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 07 QA Fail")
        run_id = uuid.uuid4()

        with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA, \
             patch("app.workflows.content_pipeline.StrategyAgent") as MockSA, \
             patch("app.workflows.content_pipeline.ScriptAgent") as MockScA, \
             patch("app.workflows.content_pipeline.SceneAgent") as MockScnA, \
             patch("app.workflows.content_pipeline.ImageAgent") as MockIA, \
             patch("app.workflows.content_pipeline.VoiceAgent") as MockVA, \
             patch("app.workflows.content_pipeline.VideoAgent") as MockVidA, \
             patch("app.quality.evaluator.run_ffprobe_inspection", new_callable=AsyncMock) as mock_ffprobe:

            # Return corrupt video with no audio track
            mock_ffprobe.return_value = {
                "valid": False, "has_video": True, "has_audio": False,
                "duration": 0.0, "size": 0, "width": 0, "height": 0,
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
            with pytest.raises(Exception):
                await pipeline.run(content.id, db, resume=False, pipeline_run_id=run_id)

        await db.refresh(content)
        assert content.status != WorkflowState.AWAITING_APPROVAL.value


# ==========================================
# 8. Worker Restart (Stale Heartbeat Recovery)
# ==========================================
@pytest.mark.asyncio
async def test_08_worker_restart_stale_job_recovery():
    await _setup_db()
    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 08 Worker Restart")
        run_id = uuid.uuid4()
        run_db = DBPipelineRun(id=run_id, content_id=content.id, status="running", current_stage="ASSETS", is_current=True)
        db.add(run_db)
        await db.flush()

        stale_time = datetime.utcnow() - timedelta(minutes=15)
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        db_job = PipelineJobDB(
            id=job_id,
            content_id=content.id,
            status="running",
            current_stage="ASSETS",
            last_heartbeat=stale_time,
            pipeline_run_id=run_id,
        )
        db.add(db_job)
        await db.commit()

    with patch("app.workflows.task_queue.enqueue_pipeline_job", new_callable=AsyncMock) as mock_enqueue:
        await recover_stale_jobs()
        assert mock_enqueue.called


# ==========================================
# 9. Redis Restart (Queued Job Recovery)
# ==========================================
@pytest.mark.asyncio
async def test_09_redis_restart_fallback():
    await _setup_db()
    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 09 Redis Restart")
        run_id = uuid.uuid4()
        run_db = DBPipelineRun(id=run_id, content_id=content.id, status="queued", current_stage="QUEUED", is_current=True)
        db.add(run_db)
        await db.flush()

        job_id = f"job_{uuid.uuid4().hex[:8]}"
        db_job = PipelineJobDB(
            id=job_id,
            content_id=content.id,
            status="queued",
            current_stage="QUEUED",
            pipeline_run_id=run_id,
        )
        db.add(db_job)
        await db.commit()

    with patch("app.workflows.task_queue.enqueue_pipeline_job", new_callable=AsyncMock) as mock_enqueue:
        await recover_queued_jobs()
        assert mock_enqueue.called


# ==========================================
# 10. API Restart (State Preservation)
# ==========================================
@pytest.mark.asyncio
async def test_10_api_restart_state_preservation():
    await _setup_db()
    cid = uuid.uuid4()
    rid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        content = DBContent(id=cid, title="Cert 10 API Restart", status="generating_assets")
        run = DBPipelineRun(id=rid, content_id=cid, status="running", current_stage="ASSETS", is_current=True)
        db.add(content)
        db.add(run)
        await db.commit()

    # Simulate fresh DB connection session (API restart)
    async with AsyncSessionLocal() as db2:
        reloaded_content = await db2.get(DBContent, cid)
        reloaded_run = await db2.get(DBPipelineRun, rid)
        assert reloaded_content.status == "generating_assets"
        assert reloaded_run.status == "running"
        assert reloaded_run.current_stage == "ASSETS"


# ==========================================
# 11. Duplicate Requests (DB-Level Active Job Guard)
# ==========================================
@pytest.mark.asyncio
async def test_11_duplicate_requests_db_active_job_guard():
    await _setup_db()
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        content = DBContent(id=cid, title="Cert 11 Duplicates", status="idea")
        db.add(content)
        await db.commit()

    # Request A creates active job
    jobA = await job_manager.create_job(content_id=str(cid), enqueue=False)
    assert jobA.status == "queued"

    # Concurrent Request B without idempotency key hits DB-level active job constraint
    jobB = await job_manager.create_job(content_id=str(cid), enqueue=False)
    # Must return the existing active job, NOT create a second duplicate job!
    assert jobB.job_id == jobA.job_id


# ==========================================
# 12. Concurrent Regeneration Guard
# ==========================================
@pytest.mark.asyncio
async def test_12_concurrent_regeneration_guard():
    await _setup_db()
    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 12 Concurrent Regen", status="rendering")
        run_id = uuid.uuid4()
        run = DBPipelineRun(id=run_id, content_id=content.id, status="running", current_stage="RENDER", is_current=True)
        db.add(run)
        await db.flush()

        active_job = PipelineJobDB(id=f"job_{uuid.uuid4().hex[:8]}", content_id=content.id, status="running", pipeline_run_id=run_id)
        db.add(active_job)
        await db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await regenerate_content(content_id=content.id, body=RegenerateBody(mode="visuals"), db=db)
        assert exc_info.value.status_code == 409


# ==========================================
# 13. Scene-Level Regeneration
# ==========================================
@pytest.mark.asyncio
async def test_13_scene_level_regeneration(tmp_path):
    await _setup_db()
    mocks = _mock_assets(tmp_path)
    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 13 Scene Regen", status="awaiting_approval")
        run_id = uuid.uuid4()
        run = DBPipelineRun(id=run_id, content_id=content.id, status="completed", current_stage="DONE", is_current=True)
        db.add(run)
        await db.flush()

        sc1 = DBScene(content_id=content.id, pipeline_run_id=run_id, scene_number=1, duration=5.0, status="completed")
        sc2 = DBScene(content_id=content.id, pipeline_run_id=run_id, scene_number=2, duration=5.0, status="completed")
        db.add(sc1)
        db.add(sc2)
        await db.flush()

        a1 = DBAsset(content_id=content.id, scene_id=sc1.id, pipeline_run_id=run_id, asset_type="image", path=mocks["img"], filename="img1.jpg", status="completed")
        a2 = DBAsset(content_id=content.id, scene_id=sc2.id, pipeline_run_id=run_id, asset_type="image", path=mocks["img"], filename="img2.jpg", status="completed")
        db.add(a1)
        db.add(a2)
        await db.commit()

        # Regenerate only scene 2
        resp = await regenerate_content(
            content_id=content.id,
            body=RegenerateBody(mode="scene", scene_number=2, reason="Improve visual contrast"),
            db=db
        )
        assert resp["mode"] == "scene"
        assert resp["scene_number"] == 2

        # Asset for scene 1 must remain untouched
        res_a1 = await db.execute(select(DBAsset).filter(DBAsset.id == a1.id))
        assert res_a1.scalars().first().status == "completed"


# ==========================================
# 14. Full Regeneration Lineage
# ==========================================
@pytest.mark.asyncio
async def test_14_full_regeneration_lineage():
    await _setup_db()
    async with AsyncSessionLocal() as db:
        content = await _create_content(db, "Cert 14 Full Regen", status="awaiting_approval")
        parent_run_id = uuid.uuid4()
        parent_run = DBPipelineRun(id=parent_run_id, content_id=content.id, status="completed", current_stage="DONE", is_current=True)
        db.add(parent_run)
        await db.commit()

        resp = await regenerate_content(
            content_id=content.id,
            body=RegenerateBody(mode="full", reason="Completely new angle"),
            db=db
        )
        assert resp["mode"] == "full"
        new_run_id = uuid.UUID(resp["pipeline_run_id"])

        new_run = await db.get(DBPipelineRun, new_run_id)
        assert new_run is not None
        assert new_run.run_type == "full_regeneration"
        assert new_run.reason == "Completely new angle"


# ==========================================
# 15. 10-Video Batch Orchestration
# ==========================================
@pytest.mark.asyncio
async def test_15_batch_10_videos_orchestration():
    await _setup_db()
    async with AsyncSessionLocal() as db:
        with patch("app.api.v1.pipeline_batch.BatchStrategyAgent") as MockBSA, \
             patch("app.api.v1.pipeline_batch.enqueue_pipeline_job", new_callable=AsyncMock) as mock_enqueue:

            variations = [
                BatchVariation(
                    angle=f"Angle {i}",
                    differentiator=f"Diff {i}",
                    title=f"Batch Video {i}",
                    hook_strategy=f"Hook {i}",
                    format_style="cinematic",
                )
                for i in range(10)
            ]
            MockBSA.return_value.generate_batch_plan = AsyncMock(
                return_value=BatchStrategyResult(
                    topic="High-Performance Systems",
                    variations=variations
                )
            )

            req = BatchPipelineRequest(topic="High-Performance Systems", count=10, platforms=["youtube_shorts"])
            resp = await trigger_batch_pipeline(req=req, db=db)

            assert resp["count"] == 10
            assert len(resp["queued_jobs"]) == 10
            assert mock_enqueue.call_count == 10


# ==========================================
# 16. 10 Videos Strict Artifact Isolation
# ==========================================
@pytest.mark.asyncio
async def test_16_batch_10_videos_strict_isolation():
    await _setup_db()
    async with AsyncSessionLocal() as db:
        c_ids = [uuid.uuid4() for _ in range(10)]
        r_ids = [uuid.uuid4() for _ in range(10)]
        for i in range(10):
            c = DBContent(id=c_ids[i], title=f"Isolated {i}", status="completed")
            r = DBPipelineRun(id=r_ids[i], content_id=c_ids[i], status="completed", current_stage="DONE", is_current=True)
            res = DBResearch(content_id=c_ids[i], pipeline_run_id=r_ids[i], summary=f"Research {i}", status="completed")
            db.add(c)
            db.add(r)
            db.add(res)
        await db.commit()

        # Query each run strictly — zero cross-run leaks
        for i in range(10):
            q = await db.execute(select(DBResearch).filter(DBResearch.content_id == c_ids[i], DBResearch.pipeline_run_id == r_ids[i]))
            rows = q.scalars().all()
            assert len(rows) == 1
            assert rows[0].summary == f"Research {i}"


# ==========================================
# 17. No External Image Provider Privacy
# ==========================================
@pytest.mark.asyncio
async def test_17_no_external_image_provider_privacy():
    assert getattr(settings, "ALLOW_EXTERNAL_GENERATION", False) is False
    service = ImageService()
    with patch("urllib.request.urlopen") as mock_http:
        path = await service.generate_image("A top-secret internal database diagram")
        mock_http.assert_not_called()
        assert os.path.exists(path)


# ==========================================
# 18. Missing FFprobe Fail-Closed QA
# ==========================================
@pytest.mark.asyncio
async def test_18_missing_ffprobe_fail_closed(tmp_path):
    qa_agent = QualityAgent()
    corrupt_file = tmp_path / "broken.mp4"
    corrupt_file.write_bytes(b"garbage data")

    with patch("app.quality.evaluator.asyncio.create_subprocess_exec", side_effect=FileNotFoundError("No ffprobe")), \
         patch("app.core.config.settings.ALLOW_QA_FALLBACK", False):
        res = await qa_agent.evaluate(
            script=None,
            scene_plan=None,
            scene_assets={},
            final_video_path=str(corrupt_file)
        )
        assert res.overall_score == 0.0
        assert res.video_score == 0.0
        assert res.passed is False


# ==========================================
# 19. Invalid Evidence / Factual Integrity
# ==========================================
def test_19_invalid_evidence_factual_integrity(tmp_path):
    generator = ThumbnailGeneratorService(output_dir=str(tmp_path))
    base = tmp_path / "base.jpg"
    Image.new("RGB", (1080, 1920), color=(10, 20, 30)).save(str(base))

    # Without verified stats, never fabricate "90% FAIL"
    candidates = generator.generate_3way_thumbnails(
        base_image_path=str(base),
        headline="Microservice Mistakes",
        stat_or_warning=None,
        verified_statistic=None,
    )
    for c in candidates:
        assert c.badge_text != "90% FAIL"


# ==========================================
# 20. Failed Job Transitions to status="failed"
# ==========================================
@pytest.mark.asyncio
async def test_20_failed_job_correctly_becomes_failed():
    await _setup_db()
    cid = uuid.uuid4()
    rid = uuid.uuid4()
    jid = f"job_{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        c = DBContent(id=cid, title="Cert 20 Worker Fail", status="idea")
        run = DBPipelineRun(id=rid, content_id=cid, status="queued", current_stage="INIT", is_current=True)
        job = PipelineJobDB(id=jid, content_id=cid, status="queued", pipeline_run_id=rid)
        db.add(c)
        db.add(run)
        await db.flush()
        db.add(job)
        await db.commit()

    with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA:
        MockRA.return_value.research_topic = AsyncMock(side_effect=RuntimeError("Unrecoverable downstream service panic"))
        with pytest.raises(RuntimeError):
            await execute_pipeline_job(
                ctx={},
                job_id=jid,
                content_id=str(cid),
                pipeline_run_id=str(rid),
                model_overrides={},
                resume=False,
            )

    async with AsyncSessionLocal() as db:
        job_db = await db.get(PipelineJobDB, jid)
        assert job_db.status == "failed"
        assert "Unrecoverable downstream service panic" in (job_db.error or "")
