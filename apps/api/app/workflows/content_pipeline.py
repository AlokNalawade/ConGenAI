import os
import uuid
import logging
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.workflows.workflow_state import WorkflowState, update_workflow_state
from app.workflows.workflow_context import WorkflowContext
from app.workflows.retry import retry_async

from app.db.models import (
    Content as DBContent,
    Research as DBResearch,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset
)

from app.agents.research import ResearchAgent
from app.agents.script import ScriptAgent
from app.agents.scene import SceneAgent
from app.agents.image import ImageAgent
from app.agents.voice import VoiceAgent
from app.agents.video import VideoAgent
from app.quality.evaluator import QualityAgent
from app.core.logging import log_manager

logger = logging.getLogger(__name__)

class ContentPipeline:
    def __init__(self):
        self.quality_agent = QualityAgent()

    async def run(
        self,
        content_id: uuid.UUID,
        db: AsyncSession,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True
    ) -> WorkflowContext:
        ctx = WorkflowContext(content_id=content_id, model_overrides=model_overrides or {})
        
        # 1. Fetch content from database
        result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
        content = result.scalars().first()
        if not content:
            err_msg = f"Content with ID {content_id} not found."
            ctx.add_error("INIT", err_msg)
            raise ValueError(err_msg)

        ctx.title = content.title or "Untitled Topic"
        ctx.platform = content.platform or "Shorts"
        ctx.idea_id = content.idea_id

        await log_manager.broadcast(
            f"🚀 Content Pipeline initiated for '{ctx.title}' ({content_id}) [Resume: {resume}]",
            agent="ContentPipeline"
        )

        try:
            # Check existing completed artifacts in DB for resumable state
            has_research = False
            has_script = False
            has_scenes = False
            has_media = False
            has_render = False

            if resume:
                # Check DBResearch
                r_res = await db.execute(select(DBResearch).filter(DBResearch.content_id == content_id).order_by(DBResearch.created_at.desc()))
                db_research = r_res.scalars().first()
                if db_research:
                    has_research = True
                    await log_manager.broadcast("⏩ [Resume] Research artifact found in DB. Skipping Research step.", agent="ContentPipeline")

                # Check DBScript
                s_res = await db.execute(select(DBScript).filter(DBScript.content_id == content_id).order_by(DBScript.created_at.desc()))
                db_script = s_res.scalars().first()
                if db_script:
                    has_script = True
                    await log_manager.broadcast("⏩ [Resume] Script artifact found in DB. Skipping Script step.", agent="ContentPipeline")

                # Check DBScenes
                sc_res = await db.execute(select(DBScene).filter(DBScene.content_id == content_id).order_by(DBScene.scene_number))
                db_scenes = sc_res.scalars().all()
                if db_scenes:
                    has_scenes = True
                    await log_manager.broadcast(f"⏩ [Resume] {len(db_scenes)} Scenes found in DB. Skipping Scene Planning step.", agent="ContentPipeline")

                # Check DBAssets
                a_res = await db.execute(select(DBAsset).filter(DBAsset.content_id == content_id))
                db_assets = a_res.scalars().all()
                vid_asset = next((a for a in db_assets if a.asset_type == "video" and os.path.exists(a.path)), None)
                if vid_asset:
                    has_render = True
                    ctx.final_video_path = vid_asset.path
                    ctx.final_video_asset_id = vid_asset.id
                    await log_manager.broadcast("⏩ [Resume] Final video asset found on disk. Skipping Render step.", agent="ContentPipeline")

            # STEP 1: RESEARCH
            if not has_research:
                await self._run_research_step(ctx, db)

            # STEP 2: SCRIPT
            if not has_script:
                await self._run_script_step(ctx, db)

            # STEP 3: SCENES
            if not has_scenes:
                await self._run_scenes_step(ctx, db)

            # STEP 4: MEDIA (Images & Voice)
            if not has_media and not has_render:
                await self._run_media_step(ctx, db)

            # STEP 5: RENDER (Video Assembly)
            if not has_render:
                await self._run_render_step(ctx, db)

            # STEP 6: QUALITY CHECK
            await self._run_quality_step(ctx, db)

            # STEP 7: TRANSITION TO AWAITING APPROVAL
            await update_workflow_state(
                db,
                content_id,
                WorkflowState.AWAITING_APPROVAL,
                quality_score=ctx.quality_result.overall_score if ctx.quality_result else None
            )
            ctx.current_state = WorkflowState.AWAITING_APPROVAL
            await log_manager.broadcast(
                f"✅ Pipeline completed successfully! Content is now AWAITING_APPROVAL.",
                agent="ContentPipeline"
            )

        except Exception as e:
            logger.error(f"Pipeline execution failed for content {content_id}: {e}", exc_info=True)
            ctx.add_error("PIPELINE", str(e))
            ctx.current_state = WorkflowState.FAILED
            await update_workflow_state(db, content_id, WorkflowState.FAILED)
            await log_manager.broadcast(
                f"❌ Pipeline failed: {str(e)}",
                agent="ContentPipeline"
            )

        return ctx

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_research_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.RESEARCH)
        ctx.current_state = WorkflowState.RESEARCH
        
        research_model = ctx.model_overrides.get("research")
        agent = ResearchAgent(model=research_model)
        
        research_res = await agent.research_topic(
            topic=ctx.title,
            target_audience=ctx.target_audience,
            platform=ctx.platform
        )
        ctx.research = research_res

        # Save to DB
        db_research = DBResearch(
            content_id=ctx.content_id,
            summary=research_res.summary,
            key_points=research_res.key_points,
            statistics=research_res.statistics,
            sources=research_res.sources,
            competitor_analysis=research_res.competitor_analysis,
            hooks=research_res.hooks,
            warnings=research_res.warnings,
        )
        db.add(db_research)
        await db.commit()

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_script_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.SCRIPT)
        ctx.current_state = WorkflowState.SCRIPT
        
        script_model = ctx.model_overrides.get("script")
        agent = ScriptAgent(model=script_model)
        
        research_dict = ctx.research.model_dump() if ctx.research else {}
        script_res = await agent.generate_script(research_data=research_dict, platform=ctx.platform)
        ctx.script = script_res

        # Save to DB
        db_script = DBScript(
            content_id=ctx.content_id,
            version=1,
            hook=script_res.hook,
            body=script_res.body,
            cta=script_res.cta,
            estimated_duration=script_res.estimated_duration,
            word_count=script_res.word_count,
            status="generated"
        )
        db.add(db_script)
        await db.commit()

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_scenes_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.SCENES)
        ctx.current_state = WorkflowState.SCENES
        
        scene_model = ctx.model_overrides.get("scene")
        agent = SceneAgent(model=scene_model)
        
        script_dict = ctx.script.model_dump() if ctx.script else {}
        scene_plan = await agent.plan_scenes(script_data=script_dict)
        ctx.scene_plan = scene_plan

        # Save DB Scenes
        for sc in scene_plan.scenes:
            db_scene = DBScene(
                content_id=ctx.content_id,
                scene_number=sc.scene_number,
                duration=sc.duration,
                narration=sc.narration,
                visual_description=sc.visual_description,
                visual_prompt=sc.visual_prompt,
                onscreen_text=sc.onscreen_text,
                transition=sc.transition,
                sound_effect=sc.sound_effect,
                status="planned"
            )
            db.add(db_scene)
        await db.commit()

    async def _run_media_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.ASSETS)
        ctx.current_state = WorkflowState.ASSETS

        # Query saved DB scenes to associate assets with DB scene IDs
        result = await db.execute(
            select(DBScene).filter(DBScene.content_id == ctx.content_id).order_by(DBScene.scene_number)
        )
        db_scenes = result.scalars().all()
        
        image_agent = ImageAgent()
        voice_agent = VoiceAgent()

        for db_sc in db_scenes:
            scene_num = db_sc.scene_number
            ctx.scene_assets[scene_num] = {}

            # 1. Generate Image Asset
            prompt = db_sc.visual_prompt or f"Scene {scene_num} for video about {ctx.title}"
            img_path = await image_agent.generate_image(prompt=prompt)
            
            img_asset = DBAsset(
                content_id=ctx.content_id,
                scene_id=db_sc.id,
                asset_type="image",
                path=img_path,
                filename=os.path.basename(img_path),
                mime_type="image/jpeg",
                provider="multi-fallback",
                model="sd-fallback"
            )
            db.add(img_asset)

            # 2. Generate Audio Asset
            narration = db_sc.narration or ctx.title
            audio_path = await voice_agent.generate_voice(text=narration)
            
            audio_asset = DBAsset(
                content_id=ctx.content_id,
                scene_id=db_sc.id,
                asset_type="audio",
                path=audio_path,
                filename=os.path.basename(audio_path),
                mime_type="audio/mp3",
                provider="edge-tts",
                model="en-US-ChristopherNeural"
            )
            db.add(audio_asset)

            await db.commit()
            
            ctx.scene_assets[scene_num] = {
                "scene_id": db_sc.id,
                "duration": db_sc.duration,
                "onscreen_text": db_sc.onscreen_text,
                "image_path": img_path,
                "audio_path": audio_path
            }

    async def _run_render_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.RENDER)
        ctx.current_state = WorkflowState.RENDER
        
        video_agent = VideoAgent()
        scene_video_paths = []

        # Render individual scene videos
        sorted_scenes = sorted(ctx.scene_assets.keys())
        for sc_num in sorted_scenes:
            data = ctx.scene_assets[sc_num]
            img_path = data["image_path"]
            audio_path = data["audio_path"]
            onscreen = data.get("onscreen_text")
            duration = data.get("duration", 5.0)

            scene_vid = await video_agent.assemble_scene(
                image_path=img_path,
                audio_path=audio_path,
                text=onscreen,
                duration=duration
            )
            scene_video_paths.append(scene_vid)
            data["video_path"] = scene_vid

        # Concatenate scene videos into final video
        final_path = await video_agent.assemble_final(scene_video_paths)
        ctx.final_video_path = final_path

        # Save Final Video Asset to DB
        final_asset = DBAsset(
            content_id=ctx.content_id,
            asset_type="video",
            path=final_path,
            filename=os.path.basename(final_path),
            mime_type="video/mp4",
            provider="ffmpeg",
            model="local-h264"
        )
        db.add(final_asset)
        await db.commit()
        await db.refresh(final_asset)
        ctx.final_video_asset_id = final_asset.id

    async def _run_quality_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.QUALITY_CHECK)
        ctx.current_state = WorkflowState.QUALITY_CHECK

        quality_res = await self.quality_agent.evaluate(
            script=ctx.script,
            scene_plan=ctx.scene_plan,
            scene_assets=ctx.scene_assets,
            final_video_path=ctx.final_video_path
        )
        ctx.quality_result = quality_res
