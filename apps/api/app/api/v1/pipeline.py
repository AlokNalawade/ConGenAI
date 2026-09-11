from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import delete
from typing import Optional, Dict, List, Literal
import uuid

from app.db.database import get_db, AsyncSessionLocal
from app.db.models import (
    Content as DBContent,
    ContentIdea as DBContentIdea,
    ContentBatch as DBContentBatch,
    PipelineRun as DBPipelineRun,
    Research as DBResearch,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset
)
from app.workflows.content_pipeline import ContentPipeline
from app.workflows.workflow_state import WorkflowState, update_workflow_state
from app.workflows.worker import job_manager

router = APIRouter()


class PipelineRequest(BaseModel):
    content_id: uuid.UUID
    model_overrides: Optional[Dict[str, str]] = None
    resume: bool = True
    idempotency_key: Optional[str] = None


class PipelineTriggerBody(BaseModel):
    model_overrides: Optional[Dict[str, str]] = None
    resume: bool = True
    idempotency_key: Optional[str] = None


class BatchPipelineRequest(BaseModel):
    topic: str = Field(..., description="Topic or prompt for content batch generation")
    count: int = Field(default=3, ge=1, le=10, description="Number of content items to generate")
    platforms: List[str] = Field(default=["youtube_shorts"], description="Target platforms")
    model_overrides: Optional[Dict[str, str]] = None


@router.post("/pipeline", status_code=status.HTTP_202_ACCEPTED)
async def trigger_content_pipeline(
    content_id: uuid.UUID,
    body: Optional[PipelineTriggerBody] = None,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    model_overrides = body.model_overrides if body else None
    resume = body.resume if body else True
    idempotency_key = body.idempotency_key if body else None

    job = await job_manager.create_job(
        content_id=str(content_id),
        model_overrides=model_overrides,
        resume=resume,
        idempotency_key=idempotency_key
    )

    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "202_accepted",
        "message": f"Pipeline job '{job.job_id}' queued for processing."
    }


@router.post("/pipeline/batch", status_code=status.HTTP_202_ACCEPTED)
async def trigger_batch_pipeline(
    req: BatchPipelineRequest,
    db: AsyncSession = Depends(get_db)
):
    from app.agents.batch_strategy import BatchStrategyAgent

    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    platform = req.platforms[0] if req.platforms else "youtube_shorts"

    # Formulate strategic angles first (before transaction)
    batch_agent = BatchStrategyAgent()
    batch_plan = await batch_agent.generate_batch_plan(topic=req.topic, count=req.count, platform=platform)

    # Issue #7: Single transaction for all Idea + Content creation
    db_batch = DBContentBatch(
        id=batch_id,
        topic=req.topic,
        requested_count=req.count,
        status="running"
    )
    db.add(db_batch)

    items = []
    for variation in batch_plan.variations:
        idea = DBContentIdea(
            title=variation.title,
            topic=req.topic,
            target_audience=variation.target_audience,
            platform=platform,
            status="approved"
        )
        db.add(idea)
        await db.flush()  # get idea.id without committing

        content = DBContent(
            idea_id=idea.id,
            batch_id=batch_id,
            title=variation.title,
            platform=platform,
            status=WorkflowState.IDEA.value
        )
        db.add(content)
        await db.flush()  # get content.id without committing
        items.append((content, variation))

    # Single commit for all batch items
    await db.commit()

    # Enqueue jobs outside the transaction
    queued_jobs = []
    for content, variation in items:
        job = await job_manager.create_job(
            content_id=str(content.id),
            model_overrides=req.model_overrides,
            resume=False
        )
        queued_jobs.append({
            "job_id": job.job_id,
            "content_id": str(content.id),
            "title": variation.title,
            "angle": variation.angle
        })

    return {
        "batch_id": batch_id,
        "topic": req.topic,
        "count": len(queued_jobs),
        "status": "202_accepted",
        "queued_jobs": queued_jobs
    }


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.post("/resume")
async def resume_content_pipeline(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    job = await job_manager.create_job(content_id=str(content_id), resume=True)
    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "status": "resumed",
        "message": f"Resuming pipeline for content {content_id} from last valid stage."
    }


@router.get("/pipeline")
async def get_pipeline_status(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    research_res = await db.execute(select(DBResearch).filter(DBResearch.content_id == content_id))
    research = research_res.scalars().first()

    script_res = await db.execute(select(DBScript).filter(DBScript.content_id == content_id).order_by(DBScript.created_at.desc()))
    script = script_res.scalars().first()

    scenes_res = await db.execute(select(DBScene).filter(DBScene.content_id == content_id))
    scenes = scenes_res.scalars().all()

    video_res = await db.execute(select(DBAsset).filter(DBAsset.content_id == content_id, DBAsset.asset_type == "video").order_by(DBAsset.created_at.desc()))
    video_asset = video_res.scalars().first()

    active_job = await job_manager.get_job_by_content(str(content_id))

    return {
        "content_id": str(content_id),
        "title": content.title,
        "status": content.status,
        "quality_score": content.quality_score,
        "has_research": research is not None,
        "has_script": script is not None,
        "scene_count": len(scenes),
        "video_asset_path": video_asset.path if video_asset else None,
        "is_approved": content.status == WorkflowState.APPROVED.value,
        "is_published": content.status == WorkflowState.PUBLISHED.value,
        "active_job": active_job.to_dict() if active_job else None
    }


@router.post("/approve")
async def approve_content(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    await update_workflow_state(db, content_id, WorkflowState.APPROVED, force=True)
    return {
        "content_id": str(content_id),
        "status": WorkflowState.APPROVED.value,
        "message": "Content successfully approved for publishing!"
    }


class RegenerateBody(BaseModel):
    mode: Literal["full", "visuals"] = Field(
        default="full",
        description=(
            "'full'    — Start a completely new pipeline run from scratch. "
            "All stages (research, strategy, script, scenes, media, render) are re-run. "
            "Use when you want a completely different angle or script.\n"
            "'visuals' — Keep the existing script and scene plan. Only regenerate "
            "images, audio, and video. 4× faster than full. "
            "Use when the script is good but you dislike the visual style."
        )
    )


@router.post("/regenerate", status_code=status.HTTP_202_ACCEPTED)
async def regenerate_content(
    content_id: uuid.UUID,
    body: Optional[RegenerateBody] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Regenerate a content item.

    mode=full (default):
        Starts a brand-new pipeline run with a fresh pipeline_run_id.
        Every stage is re-executed: research → strategy → script → scenes → media → render.
        Use when the script angle or hook was wrong.

    mode=visuals:
        Keeps the approved script and scene plan from the most recent completed run.
        Deletes only the image/audio/video assets for that run, then resumes it.
        The pipeline jumps straight to media generation (step 5), skipping all LLM steps.
        Use when the script is good but you dislike the visuals, pacing, or voice.
    """
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    mode = (body.mode if body else None) or "full"

    if mode == "visuals":
        # Find the most recent completed pipeline run for this content
        run_result = await db.execute(
            select(DBPipelineRun)
            .filter(DBPipelineRun.content_id == content_id)
            .order_by(DBPipelineRun.created_at.desc())
        )
        pipeline_run = run_result.scalars().first()

        if not pipeline_run:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No pipeline run found for this content. "
                    "Run the full pipeline first before using visuals-only mode."
                )
            )

        run_id = pipeline_run.id

        # Delete only media assets (image, audio, video, subtitle) from this run.
        # Research, strategy, script, and scene rows are left untouched.
        # hydrate_context() will reload them and skip those steps automatically.
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type.in_(["image", "audio", "video", "subtitle"]),
            )
        )

        # Reset run status so the pipeline can re-enter it
        pipeline_run.status = "queued"
        pipeline_run.current_stage = "RESUMING_VISUALS"
        pipeline_run.error = None

        # Reset content status out of awaiting_approval so the dashboard shows it as in-progress
        await update_workflow_state(db, content_id, WorkflowState.GENERATING_ASSETS)
        await db.commit()

        # Re-enqueue with resume=True and the SAME run_id.
        # hydrate_context() will find research/strategy/script/scenes (still in DB, same run_id)
        # but find no media assets (just deleted) → pipeline goes straight to step 5.
        job = await job_manager.create_job(
            content_id=str(content_id),
            resume=True,
            pipeline_run_id=str(run_id),
        )

        return {
            "job_id": job.job_id,
            "content_id": str(content_id),
            "pipeline_run_id": str(run_id),
            "mode": "visuals",
            "status": "202_accepted",
            "message": (
                "Visuals-only regeneration queued. Script and scene plan are preserved. "
                "Regenerating images, audio, and video only."
            ),
        }

    else:
        # mode=full: new pipeline_run_id, re-run everything from scratch
        job = await job_manager.create_job(content_id=str(content_id), resume=False)
        return {
            "job_id": job.job_id,
            "content_id": str(content_id),
            "pipeline_run_id": job.pipeline_run_id,
            "mode": "full",
            "status": "202_accepted",
            "message": "Full pipeline regeneration queued. All stages will be re-run from scratch.",
        }


# ---------------------------------------------------------------------------
# Pipeline Inspector — GET /inspect
# ---------------------------------------------------------------------------

@router.get("/inspect")
async def inspect_pipeline(content_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """
    Return all pipeline stage data for a content item in one call.
    Powers the Pipeline Inspector UI. Works at any point in the pipeline:
    running, paused, failed, or completed.
    """
    # Content
    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # Latest pipeline run
    run_result = await db.execute(
        select(DBPipelineRun)
        .filter(DBPipelineRun.content_id == content_id)
        .order_by(DBPipelineRun.created_at.desc())
    )
    pipeline_run = run_result.scalars().first()
    run_id = pipeline_run.id if pipeline_run else None

    # Active job
    active_job = await job_manager.get_job_by_content(str(content_id))

    # Research (scoped to latest run when available)
    research_q = select(DBResearch).filter(DBResearch.content_id == content_id)
    if run_id:
        research_q = research_q.filter(DBResearch.pipeline_run_id == run_id)
    research_res = await db.execute(research_q.order_by(DBResearch.created_at.desc()))
    research = research_res.scalars().first()

    # Strategy
    from app.db.models import Strategy as DBStrategy
    strat_q = select(DBStrategy).filter(DBStrategy.content_id == content_id)
    if run_id:
        strat_q = strat_q.filter(DBStrategy.pipeline_run_id == run_id)
    strat_res = await db.execute(strat_q.order_by(DBStrategy.created_at.desc()))
    strategy = strat_res.scalars().first()

    # Script
    script_q = select(DBScript).filter(DBScript.content_id == content_id)
    if run_id:
        script_q = script_q.filter(DBScript.pipeline_run_id == run_id)
    script_res = await db.execute(script_q.order_by(DBScript.created_at.desc()))
    script = script_res.scalars().first()

    # Scenes with their assets
    scenes_q = select(DBScene).filter(DBScene.content_id == content_id)
    if run_id:
        scenes_q = scenes_q.filter(DBScene.pipeline_run_id == run_id)
    scenes_res = await db.execute(scenes_q.order_by(DBScene.scene_number))
    scenes = scenes_res.scalars().all()

    # Assets bucketed by type and scene
    assets_q = select(DBAsset).filter(DBAsset.content_id == content_id)
    if run_id:
        assets_q = assets_q.filter(DBAsset.pipeline_run_id == run_id)
    assets_res = await db.execute(assets_q)
    all_assets = assets_res.scalars().all()

    def _asset_dict(a):
        return {
            "id": str(a.id),
            "asset_type": a.asset_type,
            "path": a.path,
            "scene_id": str(a.scene_id) if a.scene_id else None,
            "status": a.status,
            "prompt": a.prompt,
            "model": a.model,
            "duration": a.duration,
        }

    images_by_scene = {}
    audio_by_scene = {}
    video_assets = []
    for a in all_assets:
        sid = str(a.scene_id) if a.scene_id else None
        if a.asset_type == "image" and sid:
            images_by_scene[sid] = _asset_dict(a)
        elif a.asset_type == "audio" and sid:
            audio_by_scene[sid] = _asset_dict(a)
        elif a.asset_type == "video":
            video_assets.append(_asset_dict(a))

    # Agent runs for telemetry
    from app.db.models import AgentRun as DBAgentRun
    agent_q = select(DBAgentRun).filter(DBAgentRun.content_id == content_id)
    if run_id:
        agent_q = agent_q.filter(DBAgentRun.pipeline_run_id == run_id)
    agent_res = await db.execute(agent_q.order_by(DBAgentRun.created_at))
    agent_runs = agent_res.scalars().all()

    scenes_out = []
    for sc in scenes:
        sid = str(sc.id)
        scenes_out.append({
            "id": sid,
            "scene_number": sc.scene_number,
            "duration": sc.duration,
            "narration": sc.narration,
            "visual_description": sc.visual_description,
            "visual_prompt": sc.visual_prompt,
            "onscreen_text": sc.onscreen_text,
            "transition": sc.transition,
            "image_asset": images_by_scene.get(sid),
            "audio_asset": audio_by_scene.get(sid),
        })

    final_video = next(
        (a for a in video_assets if not a.get("scene_id")), None
    ) or (video_assets[0] if video_assets else None)

    return {
        "content_id": str(content_id),
        "title": content.title,
        "status": content.status,
        "quality_score": content.quality_score,
        "pipeline_run_id": str(run_id) if run_id else None,
        "pipeline_run_status": pipeline_run.status if pipeline_run else None,
        "pipeline_run_stage": pipeline_run.current_stage if pipeline_run else None,
        "pipeline_run_error": pipeline_run.error if pipeline_run else None,
        "active_job": active_job.to_dict() if active_job else None,
        "stages": {
            "research": {
                "done": research is not None,
                "summary": research.summary if research else None,
                "key_points": research.key_points if research else None,
                "hooks": research.hooks if research else None,
                "warnings": research.warnings if research else None,
            },
            "strategy": {
                "done": strategy is not None,
                "content_angle": strategy.content_angle if strategy else None,
                "target_audience": strategy.target_audience_analysis if strategy else None,
                "hook_strategy": strategy.hook_strategy if strategy else None,
                "format_guidelines": strategy.format_guidelines if strategy else None,
            },
            "script": {
                "done": script is not None,
                "hook": script.hook if script else None,
                "body": script.body if script else None,
                "cta": script.cta if script else None,
                "estimated_duration": script.estimated_duration if script else None,
                "word_count": script.word_count if script else None,
                "version": script.version if script else None,
            },
            "scenes": {
                "done": len(scenes) > 0,
                "count": len(scenes),
                "items": scenes_out,
            },
            "media": {
                "done": len(images_by_scene) > 0 or len(audio_by_scene) > 0,
                "image_count": len(images_by_scene),
                "audio_count": len(audio_by_scene),
            },
            "render": {
                "done": final_video is not None,
                "final_video": final_video,
            },
        },
        "telemetry": [
            {
                "stage": r.stage,
                "agent": r.agent,
                "model": r.model,
                "duration_seconds": round(r.duration_seconds, 2) if r.duration_seconds else None,
                "status": r.status,
                "error": r.error,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
            }
            for r in agent_runs
        ],
    }


# ---------------------------------------------------------------------------
# Stage-level re-run — POST /rerun-from/{stage}
# ---------------------------------------------------------------------------

# Which DB rows to delete when re-running from each stage.
# Each entry lists what to clear for that stage and everything downstream.
_STAGE_CLEAR_MAP = {
    "research":  ["research", "strategy", "script", "scenes", "assets"],
    "strategy":  ["strategy", "script", "scenes", "assets"],
    "script":    ["script", "scenes", "assets"],
    "scenes":    ["scenes", "assets"],
    "media":     ["assets_media"],   # only image/audio/video/subtitle
    "render":    ["assets_video"],   # only final video
}

_STAGE_TO_WORKFLOW_STATE = {
    "research": WorkflowState.RESEARCH,
    "strategy": WorkflowState.STRATEGY,
    "script":   WorkflowState.SCRIPT,
    "scenes":   WorkflowState.SCENES,
    "media":    WorkflowState.ASSETS,
    "render":   WorkflowState.RENDER,
}


@router.post("/rerun-from/{stage}", status_code=status.HTTP_202_ACCEPTED)
async def rerun_from_stage(
    content_id: uuid.UUID,
    stage: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Re-run the pipeline from a specific stage, preserving all work done before it.

    Supported stages: research, strategy, script, scenes, media, render

    Each stage clears its own DB rows plus all downstream rows, then resumes
    with the same pipeline_run_id so everything upstream is hydrated from DB.

    Examples:
      POST /rerun-from/script  → keeps research + strategy, re-runs script onwards
      POST /rerun-from/media   → keeps research/strategy/script/scenes, re-runs images/audio/video
      POST /rerun-from/render  → keeps everything, only re-renders the final video
    """
    if stage not in _STAGE_CLEAR_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage}'. Valid values: {list(_STAGE_CLEAR_MAP.keys())}"
        )

    result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
    content = result.scalars().first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # Find latest pipeline run
    run_result = await db.execute(
        select(DBPipelineRun)
        .filter(DBPipelineRun.content_id == content_id)
        .order_by(DBPipelineRun.created_at.desc())
    )
    pipeline_run = run_result.scalars().first()
    if not pipeline_run:
        raise HTTPException(
            status_code=400,
            detail="No pipeline run found. Run the full pipeline first."
        )
    run_id = pipeline_run.id

    what_to_clear = _STAGE_CLEAR_MAP[stage]

    # Clear DB rows for the chosen stage and everything downstream
    if "research" in what_to_clear:
        await db.execute(
            delete(DBResearch).where(
                DBResearch.content_id == content_id,
                DBResearch.pipeline_run_id == run_id,
            )
        )
    if "strategy" in what_to_clear:
        from app.db.models import Strategy as DBStrategy
        await db.execute(
            delete(DBStrategy).where(
                DBStrategy.content_id == content_id,
                DBStrategy.pipeline_run_id == run_id,
            )
        )
    if "script" in what_to_clear:
        await db.execute(
            delete(DBScript).where(
                DBScript.content_id == content_id,
                DBScript.pipeline_run_id == run_id,
            )
        )
    if "scenes" in what_to_clear:
        await db.execute(
            delete(DBScene).where(
                DBScene.content_id == content_id,
                DBScene.pipeline_run_id == run_id,
            )
        )
    if "assets" in what_to_clear:
        # Full asset clear — all types
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
            )
        )
    elif "assets_media" in what_to_clear:
        # Visuals only — keep no assets
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type.in_(["image", "audio", "video", "subtitle"]),
            )
        )
    elif "assets_video" in what_to_clear:
        # Final video only
        await db.execute(
            delete(DBAsset).where(
                DBAsset.content_id == content_id,
                DBAsset.pipeline_run_id == run_id,
                DBAsset.asset_type == "video",
                DBAsset.scene_id.is_(None),  # final video has no scene_id
            )
        )

    # Reset run status and content workflow state
    pipeline_run.status = "queued"
    pipeline_run.current_stage = f"RERUN_FROM_{stage.upper()}"
    pipeline_run.error = None

    target_state = _STAGE_TO_WORKFLOW_STATE[stage]
    await update_workflow_state(db, content_id, target_state, force=True)
    await db.commit()

    # Re-enqueue with resume=True + same run_id
    job = await job_manager.create_job(
        content_id=str(content_id),
        resume=True,
        pipeline_run_id=str(run_id),
    )

    return {
        "job_id": job.job_id,
        "content_id": str(content_id),
        "pipeline_run_id": str(run_id),
        "rerun_from": stage,
        "status": "202_accepted",
        "message": f"Re-running pipeline from '{stage}' stage. All upstream work is preserved.",
    }
