import os
import uuid
import logging
import asyncio
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.workflows.workflow_state import WorkflowState, update_workflow_state
from app.workflows.workflow_context import WorkflowContext
from app.workflows.retry import retry_async

from app.db.models import (
    Content as DBContent,
    Research as DBResearch,
    Strategy as DBStrategy,
    Script as DBScript,
    Scene as DBScene,
    Asset as DBAsset,
    PipelineRun as DBPipelineRun
)

from app.models.ai_contracts import (
    ResearchResult,
    StrategyResult,
    ScriptResult,
    Scene,
    ScenePlan
)

from app.agents.research import ResearchAgent
from app.agents.strategy import StrategyAgent
from app.agents.script import ScriptAgent
from app.agents.scene import SceneAgent
from app.agents.image import ImageAgent
from app.agents.voice import VoiceAgent
from app.agents.video import VideoAgent
from app.quality.evaluator import QualityAgent
from app.core.logging import log_manager
from app.core.agent_tracker import AgentTracker
from app.core.compute_config import compute_config

logger = logging.getLogger(__name__)

class ContentPipeline:
    def __init__(self):
        self.quality_agent = QualityAgent()

    async def hydrate_context(self, ctx: WorkflowContext, db: AsyncSession):
        """
        Hydrates WorkflowContext from existing database artifacts when resuming.
        """
        # 1. Research
        if not ctx.research:
            r_res = await db.execute(
                select(DBResearch)
                .filter(DBResearch.content_id == ctx.content_id, DBResearch.status == "completed")
                .order_by(DBResearch.created_at.desc())
            )
            db_research = r_res.scalars().first()
            if db_research:
                ctx.research = ResearchResult(
                    summary=db_research.summary or "",
                    key_points=db_research.key_points or [],
                    statistics=db_research.statistics or [],
                    sources=db_research.sources or [],
                    competitor_analysis=db_research.competitor_analysis or [],
                    hooks=db_research.hooks or [],
                    warnings=db_research.warnings or []
                )

        # 2. Strategy
        if not ctx.strategy:
            st_res = await db.execute(
                select(DBStrategy)
                .filter(DBStrategy.content_id == ctx.content_id, DBStrategy.status == "completed")
                .order_by(DBStrategy.created_at.desc())
            )
            db_strategy = st_res.scalars().first()
            if db_strategy:
                ctx.strategy = StrategyResult(
                    content_angle=db_strategy.content_angle or "Educational",
                    target_audience_analysis=db_strategy.target_audience_analysis or "General Audience",
                    hook_strategy=db_strategy.hook_strategy or "Curiosity Gap",
                    format_guidelines=db_strategy.format_guidelines or []
                )

        # 3. Script
        if not ctx.script:
            s_res = await db.execute(
                select(DBScript)
                .filter(DBScript.content_id == ctx.content_id, DBScript.status == "completed")
                .order_by(DBScript.created_at.desc())
            )
            db_script = s_res.scalars().first()
            if db_script:
                ctx.script = ScriptResult(
                    hook=db_script.hook or "",
                    body=db_script.body or "",
                    cta=db_script.cta or "Follow for more!",
                    estimated_duration=db_script.estimated_duration or 30,
                    word_count=db_script.word_count or 0
                )

        # 4. Scenes
        if not ctx.scene_plan:
            sc_res = await db.execute(
                select(DBScene)
                .filter(DBScene.content_id == ctx.content_id, DBScene.status == "completed")
                .order_by(DBScene.scene_number)
            )
            db_scenes = sc_res.scalars().all()
            if db_scenes:
                ctx.scene_plan = ScenePlan(scenes=[
                    Scene(
                        scene_number=sc.scene_number,
                        duration=sc.duration or 5.0,
                        narration=sc.narration or "",
                        visual_description=sc.visual_description or "",
                        visual_prompt=sc.visual_prompt or "",
                        onscreen_text=sc.onscreen_text,
                        transition=sc.transition or "none",
                        sound_effect=sc.sound_effect
                    ) for sc in db_scenes
                ])

        # 5. Scene Assets
        sc_res = await db.execute(
            select(DBScene)
            .filter(DBScene.content_id == ctx.content_id, DBScene.status == "completed")
            .order_by(DBScene.scene_number)
        )
        db_scenes = sc_res.scalars().all()
        
        a_res = await db.execute(
            select(DBAsset)
            .filter(DBAsset.content_id == ctx.content_id, DBAsset.status == "completed")
        )
        db_assets = a_res.scalars().all()

        for sc in db_scenes:
            sc_num = sc.scene_number
            img_a = next((a for a in db_assets if a.scene_id == sc.id and a.asset_type == "image" and os.path.exists(a.path) and os.path.getsize(a.path) > 100), None)
            aud_a = next((a for a in db_assets if a.scene_id == sc.id and a.asset_type == "audio" and os.path.exists(a.path) and os.path.getsize(a.path) > 100), None)
            if img_a or aud_a:
                ctx.scene_assets[sc_num] = {
                    "scene_id": sc.id,
                    "duration": sc.duration,
                    "onscreen_text": sc.onscreen_text,
                    "image_path": img_a.path if img_a else None,
                    "audio_path": aud_a.path if aud_a else None
                }

    async def run(
        self,
        content_id: uuid.UUID,
        db: AsyncSession,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True,
        pipeline_run_id: Optional[uuid.UUID] = None
    ) -> WorkflowContext:
        ctx = WorkflowContext(content_id=content_id, model_overrides=model_overrides or {})
        run_id = pipeline_run_id or uuid.uuid4()
        ctx.pipeline_run_id = run_id

        # Fetch content from database
        result = await db.execute(select(DBContent).filter(DBContent.id == content_id))
        content = result.scalars().first()
        if not content:
            err_msg = f"Content with ID {content_id} not found."
            ctx.add_error("INIT", err_msg)
            raise ValueError(err_msg)

        ctx.title = content.title or "Untitled Topic"
        ctx.platform = content.platform or "Shorts"
        ctx.idea_id = content.idea_id

        # Record PipelineRun in DB
        pipeline_run = DBPipelineRun(
            id=run_id,
            content_id=content_id,
            status="running",
            current_stage="INIT",
            model_overrides=model_overrides or {}
        )
        db.add(pipeline_run)
        await db.commit()

        await log_manager.broadcast(
            f"🚀 Content Pipeline initiated for '{ctx.title}' ({content_id}) [Run ID: {run_id}] [Resume: {resume}]",
            agent="ContentPipeline"
        )

        try:
            has_research = False
            has_strategy = False
            has_script = False
            has_scenes = False
            has_render = False

            if resume:
                await self.hydrate_context(ctx, db)

                if ctx.research:
                    has_research = True
                    await log_manager.broadcast("⏩ [Resume] Valid Research artifact loaded. Skipping Research step.", agent="ContentPipeline")

                if ctx.strategy:
                    has_strategy = True
                    await log_manager.broadcast("⏩ [Resume] Valid Strategy artifact loaded. Skipping Strategy step.", agent="ContentPipeline")

                if ctx.script:
                    has_script = True
                    await log_manager.broadcast("⏩ [Resume] Valid Script artifact loaded. Skipping Script step.", agent="ContentPipeline")

                if ctx.scene_plan:
                    has_scenes = True
                    await log_manager.broadcast(f"⏩ [Resume] {len(ctx.scene_plan.scenes)} Scenes loaded. Skipping Scene Planning step.", agent="ContentPipeline")

                # Check final video asset
                a_res = await db.execute(select(DBAsset).filter(DBAsset.content_id == content_id))
                db_assets = a_res.scalars().all()
                vid_asset = next((a for a in db_assets if a.asset_type == "video" and os.path.exists(a.path) and os.path.getsize(a.path) > 1000), None)
                if vid_asset:
                    has_render = True
                    ctx.final_video_path = vid_asset.path
                    ctx.final_video_asset_id = vid_asset.id
                    await log_manager.broadcast("⏩ [Resume] Valid final video asset found on disk. Skipping Render step.", agent="ContentPipeline")

            # STEP 1: RESEARCH
            if not has_research:
                await self._run_research_step(ctx, db)

            # STEP 2: STRATEGY
            if not has_strategy:
                await self._run_strategy_step(ctx, db)

            # STEP 3: SCRIPT
            if not has_script:
                await self._run_script_step(ctx, db)

            # STEP 4: SCENES
            if not has_scenes:
                await self._run_scenes_step(ctx, db)

            # STEP 5: MEDIA (Images & Voice - Granular scene level)
            if not has_render:
                await self._run_media_step(ctx, db)

            # STEP 6: RENDER (Video Assembly)
            if not has_render:
                await self._run_render_step(ctx, db)

            # STEP 7: QUALITY CHECK
            await self._run_quality_step(ctx, db)

            # STEP 8: TRANSITION TO AWAITING APPROVAL
            await update_workflow_state(
                db,
                content_id,
                WorkflowState.AWAITING_APPROVAL,
                quality_score=ctx.quality_result.overall_score if ctx.quality_result else None
            )
            ctx.current_state = WorkflowState.AWAITING_APPROVAL

            pipeline_run.status = "completed"
            pipeline_run.current_stage = WorkflowState.AWAITING_APPROVAL.value
            await db.commit()

            await log_manager.broadcast(
                f"✅ Pipeline completed successfully! Content is now AWAITING_APPROVAL.",
                agent="ContentPipeline"
            )

        except Exception as e:
            logger.error(f"Pipeline execution failed for content {content_id}: {e}", exc_info=True)
            ctx.add_error("PIPELINE", str(e))
            ctx.current_state = WorkflowState.FAILED
            
            pipeline_run.status = "failed"
            pipeline_run.error = str(e)
            await db.commit()

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
        
        research_model = ctx.model_overrides.get("research", compute_config.llm.model)
        agent = ResearchAgent(model=research_model)
        
        async with AgentTracker(db, ctx.content_id, "RESEARCH", "ResearchAgent", provider=compute_config.llm.provider, model=research_model, pipeline_run_id=ctx.pipeline_run_id):
            research_res = await agent.research_topic(
                topic=ctx.title,
                target_audience=ctx.target_audience,
                platform=ctx.platform
            )
        ctx.research = research_res

        db_research = DBResearch(
            content_id=ctx.content_id,
            pipeline_run_id=ctx.pipeline_run_id,
            summary=research_res.summary,
            key_points=research_res.key_points,
            statistics=research_res.statistics,
            sources=research_res.sources,
            competitor_analysis=research_res.competitor_analysis,
            hooks=research_res.hooks,
            warnings=research_res.warnings,
            status="completed"
        )
        db.add(db_research)
        await db.commit()

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_strategy_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.STRATEGY)
        ctx.current_state = WorkflowState.STRATEGY

        strategy_model = ctx.model_overrides.get("strategy", compute_config.llm.model)
        agent = StrategyAgent(model=strategy_model)

        research_dict = ctx.research.model_dump() if ctx.research else {}
        async with AgentTracker(db, ctx.content_id, "STRATEGY", "StrategyAgent", provider=compute_config.llm.provider, model=strategy_model, pipeline_run_id=ctx.pipeline_run_id):
            strategy_res = await agent.develop_strategy(
                topic=ctx.title,
                research_data=research_dict,
                platform=ctx.platform
            )
        ctx.strategy = strategy_res

        db_strategy = DBStrategy(
            content_id=ctx.content_id,
            pipeline_run_id=ctx.pipeline_run_id,
            content_angle=strategy_res.content_angle,
            target_audience_analysis=strategy_res.target_audience_analysis,
            hook_strategy=strategy_res.hook_strategy,
            format_guidelines=strategy_res.format_guidelines,
            status="completed"
        )
        db.add(db_strategy)
        await db.commit()

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_script_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.SCRIPT)
        ctx.current_state = WorkflowState.SCRIPT
        
        script_model = ctx.model_overrides.get("script", compute_config.llm.model)
        agent = ScriptAgent(model=script_model)
        
        research_dict = ctx.research.model_dump() if ctx.research else {}
        async with AgentTracker(db, ctx.content_id, "SCRIPT", "ScriptAgent", provider=compute_config.llm.provider, model=script_model, pipeline_run_id=ctx.pipeline_run_id):
            script_res = await agent.generate_script(research_data=research_dict, platform=ctx.platform)
        ctx.script = script_res

        db_script = DBScript(
            content_id=ctx.content_id,
            pipeline_run_id=ctx.pipeline_run_id,
            version=1,
            hook=script_res.hook,
            body=script_res.body,
            cta=script_res.cta,
            estimated_duration=script_res.estimated_duration,
            word_count=script_res.word_count,
            status="completed"
        )
        db.add(db_script)
        await db.commit()

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_scenes_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.SCENES)
        ctx.current_state = WorkflowState.SCENES
        
        scene_model = ctx.model_overrides.get("scene", compute_config.llm.model)
        agent = SceneAgent(model=scene_model)
        
        script_dict = ctx.script.model_dump() if ctx.script else {}
        async with AgentTracker(db, ctx.content_id, "SCENES", "SceneAgent", provider=compute_config.llm.provider, model=scene_model, pipeline_run_id=ctx.pipeline_run_id):
            scene_plan = await agent.plan_scenes(script_data=script_dict)

        # Validate ScenePlan consistency
        target_dur = ctx.script.estimated_duration if ctx.script else None
        scene_plan.validate_consistency(target_duration=target_dur)
        ctx.scene_plan = scene_plan

        for sc in scene_plan.scenes:
            db_scene = DBScene(
                content_id=ctx.content_id,
                pipeline_run_id=ctx.pipeline_run_id,
                scene_number=sc.scene_number,
                duration=sc.duration,
                narration=sc.narration,
                visual_description=sc.visual_description,
                visual_prompt=sc.visual_prompt,
                onscreen_text=sc.onscreen_text,
                transition=sc.transition,
                sound_effect=sc.sound_effect,
                status="completed"
            )
            db.add(db_scene)
        await db.commit()

    async def _run_media_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.ASSETS)
        ctx.current_state = WorkflowState.ASSETS

        result = await db.execute(
            select(DBScene).filter(DBScene.content_id == ctx.content_id).order_by(DBScene.scene_number)
        )
        db_scenes = result.scalars().all()
        
        # Load existing assets to skip completed scene assets
        a_res = await db.execute(
            select(DBAsset).filter(DBAsset.content_id == ctx.content_id, DBAsset.status == "completed")
        )
        existing_assets = a_res.scalars().all()

        image_agent = ImageAgent()
        voice_agent = VoiceAgent()

        img_sem = asyncio.Semaphore(compute_config.image_concurrency)
        tts_sem = asyncio.Semaphore(compute_config.tts_concurrency)

        async def _process_scene_assets(scene_num: int, scene_db_id: uuid.UUID, prompt: str, narration: str, scene_dur: float):
            # Check existing image asset
            existing_img = next((a for a in existing_assets if a.scene_id == scene_db_id and a.asset_type == "image" and os.path.exists(a.path) and os.path.getsize(a.path) > 100), None)
            if existing_img:
                img_path = existing_img.path
            else:
                async with img_sem:
                    async with AgentTracker(db, ctx.content_id, "ASSETS_IMAGE", "ImageAgent", provider=compute_config.image.provider, model=compute_config.image.model, pipeline_run_id=ctx.pipeline_run_id):
                        img_path = await image_agent.generate_image(prompt=prompt)
            
            # Check existing audio asset
            existing_aud = next((a for a in existing_assets if a.scene_id == scene_db_id and a.asset_type == "audio" and os.path.exists(a.path) and os.path.getsize(a.path) > 100), None)
            if existing_aud:
                audio_path = existing_aud.path
                actual_duration = existing_aud.duration or scene_dur
            else:
                async with tts_sem:
                    async with AgentTracker(db, ctx.content_id, "ASSETS_VOICE", "VoiceAgent", provider=compute_config.tts.provider, model=compute_config.tts.model, pipeline_run_id=ctx.pipeline_run_id):
                        audio_path = await voice_agent.generate_voice(text=narration)

                actual_duration = scene_dur
                if audio_path and os.path.exists(audio_path):
                    try:
                        import wave
                        with wave.open(audio_path, 'r') as wf:
                            frames = wf.getnframes()
                            rate = wf.getframerate()
                            if rate > 0:
                                actual_duration = round(frames / float(rate), 2)
                    except Exception:
                        pass

            return scene_num, scene_db_id, prompt, img_path, audio_path, actual_duration, existing_img is not None, existing_aud is not None

        tasks = [
            _process_scene_assets(
                sc.scene_number,
                sc.id,
                sc.visual_prompt or f"Scene {sc.scene_number} for video about {ctx.title}",
                sc.narration or ctx.title,
                sc.duration
            )
            for sc in db_scenes
        ]
        media_results = await asyncio.gather(*tasks)

        for scene_num, scene_db_id, prompt, img_path, audio_path, actual_duration, had_img, had_aud in media_results:
            ctx.scene_assets[scene_num] = {}

            if not had_img:
                img_asset = DBAsset(
                    content_id=ctx.content_id,
                    scene_id=scene_db_id,
                    pipeline_run_id=ctx.pipeline_run_id,
                    asset_type="image",
                    path=img_path,
                    filename=os.path.basename(img_path),
                    mime_type="image/jpeg",
                    provider=compute_config.image.provider,
                    model=compute_config.image.model,
                    prompt=prompt,
                    status="completed"
                )
                db.add(img_asset)

            if not had_aud:
                audio_asset = DBAsset(
                    content_id=ctx.content_id,
                    scene_id=scene_db_id,
                    pipeline_run_id=ctx.pipeline_run_id,
                    asset_type="audio",
                    path=audio_path,
                    filename=os.path.basename(audio_path),
                    mime_type="audio/mp3",
                    duration=actual_duration,
                    provider=compute_config.tts.provider,
                    model=compute_config.tts.model,
                    status="completed"
                )
                db.add(audio_asset)

            ctx.scene_assets[scene_num] = {
                "scene_id": scene_db_id,
                "duration": actual_duration,
                "onscreen_text": next((sc.onscreen_text for sc in db_scenes if sc.scene_number == scene_num), None),
                "image_path": img_path,
                "audio_path": audio_path
            }

        await db.commit()

    async def _run_render_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.RENDER)
        ctx.current_state = WorkflowState.RENDER
        
        video_agent = VideoAgent()
        scene_video_paths = []

        sorted_scenes = sorted(ctx.scene_assets.keys())
        async with AgentTracker(db, ctx.content_id, "RENDER", "VideoAgent", provider="ffmpeg", model="local-h264", pipeline_run_id=ctx.pipeline_run_id):
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

            final_path = await video_agent.assemble_final(scene_video_paths)
        
        ctx.final_video_path = final_path

        final_asset = DBAsset(
            content_id=ctx.content_id,
            pipeline_run_id=ctx.pipeline_run_id,
            asset_type="video",
            path=final_path,
            filename=os.path.basename(final_path),
            mime_type="video/mp4",
            provider="ffmpeg",
            model="local-h264",
            status="completed"
        )
        db.add(final_asset)
        await db.commit()
        await db.refresh(final_asset)
        ctx.final_video_asset_id = final_asset.id

    async def _run_quality_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.QUALITY_CHECK)
        ctx.current_state = WorkflowState.QUALITY_CHECK

        async with AgentTracker(db, ctx.content_id, "QUALITY_CHECK", "QualityAgent", provider="internal", model="evaluator-v1", pipeline_run_id=ctx.pipeline_run_id):
            quality_res = await self.quality_agent.evaluate(
                script=ctx.script,
                scene_plan=ctx.scene_plan,
                scene_assets=ctx.scene_assets,
                final_video_path=ctx.final_video_path
            )
        ctx.quality_result = quality_res
