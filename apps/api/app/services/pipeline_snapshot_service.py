"""
Unified PipelineSnapshotService.

Provides canonical PipelineRun resolution and consistent pipeline status snapshots
for both summary (GET /pipeline) and detailed inspection (GET /inspect).
"""
import uuid
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.models import (
    Content as DBContent,
    PipelineRun as DBPipelineRun,
    Research as DBResearch,
    Strategy as DBStrategy,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset,
    AgentRun as DBAgentRun,
)
from app.workflows.worker import job_manager
from app.workflows.workflow_state import WorkflowState


class PipelineSnapshotService:
    @staticmethod
    async def resolve_canonical_run(
        db: AsyncSession,
        content_id: uuid.UUID,
    ) -> Optional[DBPipelineRun]:
        """
        Determine the canonical/valid PipelineRun for a content item:
        1. Explicit flag: run with is_current == True.
        2. Active run: run with status in ('queued', 'running') for live tracking.
        3. Most recent completed run: so a failed re-run does not hide previously successful assets.
        4. Run with a completed final video asset.
        5. Fallback to latest run by created_at desc.
        """
        res = await db.execute(
            select(DBPipelineRun)
            .filter(DBPipelineRun.content_id == content_id)
            .order_by(DBPipelineRun.created_at.desc())
        )
        runs = res.scalars().all()
        if not runs:
            return None

        # 1. Check explicit is_current flag
        for r in runs:
            if getattr(r, "is_current", False):
                return r

        # 2. Check active execution
        for r in runs:
            if r.status in ("queued", "running"):
                return r

        # 3. Check most recent completed run
        for r in runs:
            if r.status == "completed":
                return r

        # 4. Check run with completed video asset
        for r in runs:
            asset_res = await db.execute(
                select(DBAsset).filter(
                    DBAsset.pipeline_run_id == r.id,
                    DBAsset.asset_type == "video",
                    DBAsset.status == "completed",
                    DBAsset.scene_id.is_(None),
                )
            )
            if asset_res.scalars().first():
                return r

        # 5. Fallback to latest by created_at
        return runs[0]

    @staticmethod
    async def get_snapshot(
        db: AsyncSession,
        content_id: uuid.UUID,
        run_id: Optional[uuid.UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Produce a comprehensive inspection snapshot for a content item and its canonical run.
        """
        result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
        content = result.scalars().first()
        if not content:
            return None

        if run_id:
            run_res = await db.execute(select(DBPipelineRun).filter(DBPipelineRun.id == run_id))
            pipeline_run = run_res.scalars().first()
        else:
            pipeline_run = await PipelineSnapshotService.resolve_canonical_run(db, content_id)

        actual_run_id = pipeline_run.id if pipeline_run else None

        active_job = await job_manager.get_job_by_content(str(content_id))

        # Research
        research_q = select(DBResearch).filter(DBResearch.content_id == content_id)
        if actual_run_id:
            research_q = research_q.filter(DBResearch.pipeline_run_id == actual_run_id)
        research_res = await db.execute(research_q.order_by(DBResearch.created_at.desc()))
        research = research_res.scalars().first()

        # Strategy
        strat_q = select(DBStrategy).filter(DBStrategy.content_id == content_id)
        if actual_run_id:
            strat_q = strat_q.filter(DBStrategy.pipeline_run_id == actual_run_id)
        strat_res = await db.execute(strat_q.order_by(DBStrategy.created_at.desc()))
        strategy = strat_res.scalars().first()

        # Script
        script_q = select(DBScript).filter(DBScript.content_id == content_id)
        if actual_run_id:
            script_q = script_q.filter(DBScript.pipeline_run_id == actual_run_id)
        script_res = await db.execute(script_q.order_by(DBScript.created_at.desc()))
        script = script_res.scalars().first()

        # Scenes
        scenes_q = select(DBScene).filter(DBScene.content_id == content_id)
        if actual_run_id:
            scenes_q = scenes_q.filter(DBScene.pipeline_run_id == actual_run_id)
        scenes_res = await db.execute(scenes_q.order_by(DBScene.scene_number))
        scenes = scenes_res.scalars().all()

        # Assets
        assets_q = select(DBAsset).filter(DBAsset.content_id == content_id)
        if actual_run_id:
            assets_q = assets_q.filter(DBAsset.pipeline_run_id == actual_run_id)
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

        # Agent runs
        agent_q = select(DBAgentRun).filter(DBAgentRun.content_id == content_id)
        if actual_run_id:
            agent_q = agent_q.filter(DBAgentRun.pipeline_run_id == actual_run_id)
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
            "pipeline_run_id": str(actual_run_id) if actual_run_id else None,
            "pipeline_run_status": pipeline_run.status if pipeline_run else None,
            "pipeline_run_stage": pipeline_run.current_stage if pipeline_run else None,
            "pipeline_run_error": pipeline_run.error if pipeline_run else None,
            "run_type": getattr(pipeline_run, "run_type", None) if pipeline_run else None,
            "parent_run_id": str(pipeline_run.parent_run_id) if (pipeline_run and getattr(pipeline_run, "parent_run_id", None)) else None,
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

    @staticmethod
    async def get_summary_status(
        db: AsyncSession,
        content_id: uuid.UUID,
    ) -> Optional[Dict[str, Any]]:
        """
        Produce concise pipeline status using canonical run resolution.
        Ensures GET /pipeline is run-aware and consistent with /inspect.
        """
        snapshot = await PipelineSnapshotService.get_snapshot(db, content_id)
        if not snapshot:
            return None

        final_video = snapshot["stages"]["render"]["final_video"]
        video_path = final_video.get("path") if final_video else None

        return {
            "content_id": snapshot["content_id"],
            "title": snapshot["title"],
            "status": snapshot["status"],
            "quality_score": snapshot["quality_score"],
            "pipeline_run_id": snapshot["pipeline_run_id"],
            "pipeline_run_status": snapshot["pipeline_run_status"],
            "pipeline_run_stage": snapshot["pipeline_run_stage"],
            "has_research": snapshot["stages"]["research"]["done"],
            "has_strategy": snapshot["stages"]["strategy"]["done"],
            "has_script": snapshot["stages"]["script"]["done"],
            "scene_count": snapshot["stages"]["scenes"]["count"],
            "video_asset_path": video_path,
            "is_approved": snapshot["status"] == WorkflowState.APPROVED.value,
            "is_published": snapshot["status"] == WorkflowState.PUBLISHED.value,
            "active_job": snapshot["active_job"],
        }
