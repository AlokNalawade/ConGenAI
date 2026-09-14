"""Unit and integration tests for production readiness fixes:
1. Pipeline failure propagation & worker job failure marking
2. ImageService local-first privacy (ALLOW_EXTERNAL_GENERATION=False)
3. Evidence integrity & Platform-aware thumbnails
4. B-roll anti-repetition & Kinetic subtitle burst formatting
"""

import pytest
import os
import uuid
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
from PIL import Image

from app.core.config import settings
from app.workflows.workflow_state import WorkflowState
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.task_queue import execute_pipeline_job
from app.services.image_service import ImageService
from app.services.thumbnail_generator import ThumbnailGeneratorService, ThumbnailStyle
from app.services.broll_service import BRollService
from app.db.database import AsyncSessionLocal
from app.db.init_db import init_db
from app.db.models import Content as DBContent, PipelineRun as DBPipelineRun, PipelineJobDB


@pytest.fixture(autouse=True)
def ensure_external_disabled():
    """Ensure external network generation is disabled by default for privacy."""
    old_val = getattr(settings, "ALLOW_EXTERNAL_GENERATION", False)
    settings.ALLOW_EXTERNAL_GENERATION = False
    yield
    settings.ALLOW_EXTERNAL_GENERATION = old_val


@pytest.mark.asyncio
async def test_image_service_privacy_guarantee():
    """Verify ImageService strictly avoids external network requests when ALLOW_EXTERNAL_GENERATION=False."""
    service = ImageService()

    with patch("urllib.request.urlopen") as mock_urlopen:
        img_path = await service.generate_image("A futuristic cyber terminal with code")
        
        # Verify no external HTTP calls were initiated
        mock_urlopen.assert_not_called()
        assert os.path.exists(img_path)
        img = Image.open(img_path)
        assert img.size == (1080, 1920)


@pytest.mark.asyncio
async def test_pipeline_failure_raises_and_marks_worker_job_failed():
    """Verify that when a pipeline step fails, ContentPipeline.run(raise_on_failure=True) raises
    and execute_pipeline_job updates PipelineJobDB.status = 'failed'."""
    await init_db()

    async with AsyncSessionLocal() as db:
        # Create test content
        content = DBContent(
            id=uuid.uuid4(),
            title="Production Pipeline Failure Test",
            description="Testing",
            platform="Shorts",
            status=WorkflowState.IDEA.value,
        )
        db.add(content)

        # Create pipeline run and job
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        run_id = uuid.uuid4()
        run_db = DBPipelineRun(
            id=run_id,
            content_id=content.id,
            status="queued",
            current_stage="INIT",
            is_current=True,
        )
        db.add(run_db)
        await db.flush()

        job = PipelineJobDB(
            id=job_id,
            content_id=content.id,
            status="queued",
            pipeline_run_id=run_id,
        )
        db.add(job)
        await db.commit()
        content_id = content.id

    # Mock ResearchAgent to fail
    with patch("app.workflows.content_pipeline.ResearchAgent") as MockRA:
        MockRA.return_value.research_topic = AsyncMock(
            side_effect=RuntimeError("Simulated LLM API rate limit error")
        )

        # Execute via worker job executor
        with pytest.raises(RuntimeError) as excinfo:
            await execute_pipeline_job(
                ctx={},
                job_id=job_id,
                content_id=str(content_id),
                pipeline_run_id=str(uuid.uuid4()),
                model_overrides={},
                resume=False,
            )

        assert "Simulated LLM API rate limit error" in str(excinfo.value)

    # Verify that the database record is NOT 'completed' - it MUST be 'failed'
    async with AsyncSessionLocal() as db:
        job_db = await db.get(PipelineJobDB, job_id)
        assert job_db is not None
        assert job_db.status == "failed"
        assert "Simulated LLM API rate limit error" in (job_db.error or "")


@pytest.mark.asyncio
async def test_thumbnail_generator_verified_evidence_and_resolutions():
    """Verify ThumbnailGeneratorService uses verified statistics and never fabricates claims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base_scene.png")
        base_img = Image.new("RGB", (1080, 1920), color=(15, 20, 30))
        base_img.save(base_path)

        generator = ThumbnailGeneratorService(output_dir=os.path.join(tmpdir, "thumbs"))

        # Case 1: 9:16 Shorts thumbnail with no verified statistics
        candidates = generator.generate_3way_thumbnails(
            base_image_path=base_path,
            headline="Why Architecture Matters",
            target_resolution=(1080, 1920),
        )
        for c in candidates:
            assert "90% FAIL" not in (c.badge_text or "")

        # Case 2: 16:9 YouTube thumbnail with verified statistic
        yt_candidates = generator.generate_3way_thumbnails(
            base_image_path=base_path,
            headline="Why Architecture Matters",
            verified_statistic="4.2x HIGHER THROUGHPUT",
            target_resolution=(1280, 720),
        )
        stat_c = next(c for c in yt_candidates if c.style == ThumbnailStyle.STATISTIC_PROOF)
        assert stat_c.badge_text == "4.2x HIGHER THROUGHPUT"
        img = Image.open(stat_c.image_path)
        assert img.size == (1280, 720)
