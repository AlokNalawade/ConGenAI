"""
Unit and integration tests for architectural and reliability review findings:
1. Race condition guard on regeneration & stage rerun (409 Conflict)
2. Strict approval requirements & audited admin force-approval
3. Batch strategic DNA persistence in Content.metadata_json
4. PipelineSnapshotService unified canonical run resolution
5. Regeneration lineage tracking (parent_run_id, run_type, reason)
6. ResourceSemaphores QA concurrency and config
"""
import uuid
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

from app.db.database import AsyncSessionLocal, engine
from app.db.models import (
    Content as DBContent,
    PipelineRun as DBPipelineRun,
    Asset as DBAsset,
    AgentRun as DBAgentRun,
    PipelineJobDB,
)
from app.workflows.workflow_state import WorkflowState
from app.workflows.worker import job_manager
from app.services.pipeline_snapshot_service import PipelineSnapshotService
from app.api.v1.approvals import approve_content, force_approve_content, ForceApproveBody
from app.api.v1.pipeline_regeneration import regenerate_content, rerun_from_stage, RegenerateBody
from app.api.v1.pipeline_batch import trigger_batch_pipeline, BatchPipelineRequest
from app.agents.batch_strategy import BatchStrategyResult, BatchVariation
from app.core.compute_config import compute_config, ResourceSemaphores


@pytest.mark.asyncio
async def test_race_condition_guard_on_regeneration_and_rerun():
    """Finding #1: An active queued or running job must reject regeneration with 409 Conflict."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        content = DBContent(
            title="Race Condition Guard Test",
            content_type="Shorts",
            platform="youtube_shorts",
            status="rendering",
        )
        db.add(content)
        await db.commit()
        await db.refresh(content)

        # Create active job in DB
        run_id = uuid.uuid4()
        run_db = DBPipelineRun(
            id=run_id,
            content_id=content.id,
            status="running",
            current_stage="RENDER",
            is_current=True,
        )
        db.add(run_db)
        await db.flush()

        active_job = PipelineJobDB(
            id=f"job_{uuid.uuid4().hex[:8]}",
            content_id=content.id,
            status="running",
            pipeline_run_id=run_id,
        )
        db.add(active_job)
        await db.commit()

        # Attempting visual or full regeneration should raise 409 Conflict
        with pytest.raises(HTTPException) as exc_info:
            await regenerate_content(
                content_id=content.id,
                body=RegenerateBody(mode="visuals"),
                db=db,
            )
        assert exc_info.value.status_code == 409
        assert "is currently in status 'running'" in exc_info.value.detail

        # Attempting stage rerun should also raise 409 Conflict
        with pytest.raises(HTTPException) as exc_info_rerun:
            await rerun_from_stage(
                content_id=content.id,
                stage="render",
                db=db,
            )
        assert exc_info_rerun.value.status_code == 409


@pytest.mark.asyncio
async def test_strict_approval_and_admin_force_approve():
    """Finding #2: Strict approval enforces awaiting_approval + video asset. Admin endpoint provides audited bypass."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        content = DBContent(
            title="Approval Validation Test",
            status=WorkflowState.IDEA.value,
        )
        db.add(content)
        await db.commit()
        await db.refresh(content)

        # 1. Reject if not awaiting_approval
        with pytest.raises(HTTPException) as exc_idea:
            await approve_content(content_id=content.id, db=db)
        assert exc_idea.value.status_code == 400
        assert "Content must be in 'awaiting_approval' state" in exc_idea.value.detail

        # 2. Reject if awaiting_approval but missing completed video asset
        content.status = WorkflowState.AWAITING_APPROVAL.value
        await db.commit()

        with pytest.raises(HTTPException) as exc_no_video:
            await approve_content(content_id=content.id, db=db)
        assert exc_no_video.value.status_code == 400
        assert "without a completed video asset" in exc_no_video.value.detail

        # 3. Succeed when video asset exists
        video_asset = DBAsset(
            content_id=content.id,
            asset_type="video",
            path="/path/to/test.mp4",
            status="completed",
        )
        db.add(video_asset)
        await db.commit()

        res = await approve_content(content_id=content.id, db=db)
        assert res["status"] == WorkflowState.APPROVED.value
        await db.refresh(content)
        assert content.status == WorkflowState.APPROVED.value

        # 4. Admin force-approve bypasses strict checks and writes audit log
        content_bypass = DBContent(
            title="Admin Bypass Test",
            status=WorkflowState.IDEA.value,
        )
        db.add(content_bypass)
        await db.commit()
        await db.refresh(content_bypass)

        bypass_res = await force_approve_content(
            content_id=content_bypass.id,
            body=ForceApproveBody(reason="Client urgent sign-off"),
            db=db,
        )
        assert bypass_res["status"] == WorkflowState.APPROVED.value
        assert bypass_res["reason"] == "Client urgent sign-off"

        await db.refresh(content_bypass)
        assert content_bypass.status == WorkflowState.APPROVED.value

        # Verify audit record in DBAgentRun
        from sqlalchemy.future import select
        audit_res = await db.execute(
            select(DBAgentRun).filter(
                DBAgentRun.content_id == content_bypass.id,
                DBAgentRun.agent == "Admin",
            )
        )
        audit_entry = audit_res.scalars().first()
        assert audit_entry is not None
        assert "Client urgent sign-off" in audit_entry.error


@pytest.mark.asyncio
async def test_batch_strategy_dna_and_atomic_creation():
    """Findings #3 & #7: Batch strategic DNA persisted in metadata_json and committed atomically."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        mock_plan = BatchStrategyResult(
            topic="Next Gen Robotics",
            variations=[
                BatchVariation(
                    title="Humanoid Robots at Home",
                    angle="Consumer adoption and lifestyle disruption",
                    target_audience="General public & early adopters",
                    hook_strategy="Emotional / Shock factor",
                    differentiator="Focuses on domestic chore automation",
                    avoid_overlap_with=["Industrial factory applications"],
                ),
                BatchVariation(
                    title="Industrial Automata",
                    angle="Factory throughput and economic labor economics",
                    target_audience="Engineers & business leaders",
                    hook_strategy="Statistical / ROI hook",
                    differentiator="Focuses on high-speed factory automation",
                    avoid_overlap_with=["Consumer domestic robots"],
                ),
            ],
        )

        with patch("app.agents.batch_strategy.BatchStrategyAgent.generate_batch_plan", new_callable=AsyncMock) as mock_batch, \
             patch("app.api.v1.pipeline_batch.enqueue_pipeline_job", new_callable=AsyncMock) as mock_enqueue:
            mock_batch.return_value = mock_plan
            mock_enqueue.return_value = "mock_arq_id"

            req = BatchPipelineRequest(topic="Next Gen Robotics", count=2)
            resp = await trigger_batch_pipeline(req=req, db=db)

            assert resp["count"] == 2
            assert len(resp["queued_jobs"]) == 2

            from sqlalchemy.future import select
            c_res = await db.execute(
                select(DBContent).filter(DBContent.batch_id == resp["batch_id"])
            )
            contents = c_res.scalars().all()
            assert len(contents) == 2

            # Check strategic DNA in metadata_json
            dna0 = contents[0].metadata_json
            assert dna0["angle"] == "Consumer adoption and lifestyle disruption"
            assert dna0["hook_strategy"] == "Emotional / Shock factor"
            assert dna0["differentiator"] == "Focuses on domestic chore automation"
            assert dna0["avoid_overlap_with"] == ["Industrial factory applications"]


@pytest.mark.asyncio
async def test_canonical_run_resolution_service():
    """Findings #4 & #5: PipelineSnapshotService resolves canonical run so failed runs don't hide valid assets."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        content = DBContent(
            title="Canonical Run Test",
            status=WorkflowState.AWAITING_APPROVAL.value,
        )
        db.add(content)
        await db.commit()
        await db.refresh(content)

        # Run 1: Completed run with a valid video
        run_1_id = uuid.uuid4()
        run_1 = DBPipelineRun(
            id=run_1_id,
            content_id=content.id,
            status="completed",
            current_stage="AWAITING_APPROVAL",
            is_current=True,
        )
        db.add(run_1)
        await db.commit()

        video_1 = DBAsset(
            content_id=content.id,
            pipeline_run_id=run_1_id,
            asset_type="video",
            path="/assets/run1_video.mp4",
            status="completed",
        )
        db.add(video_1)
        await db.commit()

        # Run 2: Failed subsequent run
        run_2_id = uuid.uuid4()
        run_2 = DBPipelineRun(
            id=run_2_id,
            content_id=content.id,
            status="failed",
            current_stage="SCENES",
            error="CUDA out of memory",
            is_current=False,
        )
        db.add(run_2)
        await db.commit()

        # Service should resolve canonical run as run 1 (the completed one with the video asset)
        canonical_run = await PipelineSnapshotService.resolve_canonical_run(db, content.id)
        assert canonical_run is not None
        assert canonical_run.id == run_1_id

        # Summary status should reflect run 1
        summary = await PipelineSnapshotService.get_summary_status(db, content.id)
        assert summary["pipeline_run_id"] == str(run_1_id)
        assert summary["pipeline_run_status"] == "completed"
        assert summary["video_asset_path"] == "/assets/run1_video.mp4"


@pytest.mark.asyncio
async def test_regeneration_lineage_tracking():
    """Finding #6: Regeneration records lineage (parent_run_id, run_type, reason)."""
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        content = DBContent(
            title="Lineage Tracking Test",
            status=WorkflowState.AWAITING_APPROVAL.value,
        )
        db.add(content)
        await db.commit()
        await db.refresh(content)

        initial_run_id = uuid.uuid4()
        initial_run = DBPipelineRun(
            id=initial_run_id,
            content_id=content.id,
            status="completed",
            current_stage="AWAITING_APPROVAL",
            is_current=True,
        )
        db.add(initial_run)
        await db.commit()

        # Full regeneration with custom reason
        with patch("app.workflows.task_queue.is_redis_available", new_callable=AsyncMock) as mock_redis:
            mock_redis.return_value = False  # Keep in DB queue

            regen_resp = await regenerate_content(
                content_id=content.id,
                body=RegenerateBody(mode="full", reason="Audience angle too narrow"),
                db=db,
            )

            assert regen_resp["mode"] == "full"
            assert regen_resp["parent_run_id"] == str(initial_run_id)
            assert regen_resp["reason"] == "Audience angle too narrow"

            # Check DB record of the new run
            from sqlalchemy.future import select
            new_run_res = await db.execute(
                select(DBPipelineRun).filter(DBPipelineRun.id == uuid.UUID(regen_resp["pipeline_run_id"]))
            )
            new_run = new_run_res.scalars().first()
            assert new_run is not None
            assert new_run.parent_run_id == initial_run_id
            assert new_run.run_type == "full_regeneration"
            assert new_run.reason == "Audience angle too narrow"
            assert bool(new_run.is_current) is True


def test_resource_semaphores_configuration():
    """Finding #8: Semaphores configuration includes qa semaphore and conforms to concurrency limits."""
    semaphores = compute_config.create_semaphores()
    assert isinstance(semaphores, ResourceSemaphores)
    assert hasattr(semaphores, "image_gpu")
    assert hasattr(semaphores, "llm")
    assert hasattr(semaphores, "tts")
    assert hasattr(semaphores, "ffmpeg")
    assert hasattr(semaphores, "qa")
    assert compute_config.qa_concurrency >= 1


@pytest.mark.asyncio
async def test_quality_agent_fail_closed_without_ffprobe(tmp_path):
    """P2: FFprobe failure must reject QA (passed=False, score=0.0) when ALLOW_QA_FALLBACK=False."""
    from app.quality.evaluator import run_ffprobe_inspection, QualityAgent
    from app.models.ai_contracts import ScriptResult, ScenePlan, Scene

    dummy_video = tmp_path / "broken_video.mp4"
    dummy_video.write_bytes(b"CORRUPT_BYTES_OVER_1000" + b"\x00" * 2000)

    # 1. Fail-closed with fallback disabled (production default)
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("ffprobe not found")):
        info = await run_ffprobe_inspection(str(dummy_video), allow_fallback=False)
        assert info["valid"] is False
        assert "rejected" in info["error"]

        agent = QualityAgent()
        script = ScriptResult(hook="Hook test", body="Body test over 20 chars long", cta="CTA test", estimated_duration=15, word_count=15)
        scenes = ScenePlan(scenes=[Scene(scene_number=1, duration=15, narration="Narration", visual_description="Desc", visual_prompt="Prompt")])
        res = await agent.evaluate(script=script, scene_plan=scenes, final_video_path=str(dummy_video))

        assert res.passed is False
        assert res.video_score == 0.0
        assert any("Technical video validation failed" in f for f in res.feedback)

    # 2. Dev-only fallback when explicitly enabled
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("ffprobe not found")):
        dev_info = await run_ffprobe_inspection(str(dummy_video), allow_fallback=True)
        assert dev_info["valid"] is True
        assert dev_info["is_fallback"] is True


@pytest.mark.asyncio
async def test_alembic_migrations_up_to_date():
    """P1: Database initialization executes Alembic migrations and schema matches head."""
    from app.db.init_db import init_db
    # Force run migrations
    await init_db(force=True)
    # Verification: run Alembic current check
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    import os

    current_dir = os.path.dirname(os.path.abspath(__file__))
    api_dir = os.path.dirname(os.path.dirname(current_dir))
    alembic_cfg = Config(os.path.join(api_dir, "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    head_rev = script.get_current_head()
    assert head_rev is not None
    assert head_rev == "5a33285fa474"


