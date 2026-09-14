import os
import uuid
import logging
import asyncio
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update

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
from app.core.compute_config import compute_config, ResourceSemaphores
from app.core.model_manager import ModelManager
from app.core.model_router import ModelRouter

logger = logging.getLogger(__name__)

class ContentPipeline:
    def __init__(
        self,
        model_manager: Optional[ModelManager] = None,
        model_router: Optional[ModelRouter] = None,
        semaphores: Optional[ResourceSemaphores] = None,
    ):
        self.quality_agent = QualityAgent()
        self.model_manager = model_manager or ModelManager.for_profile(compute_config.profile)
        self.model_router = model_router or ModelRouter.for_profile(compute_config.profile)
        self.semaphores = semaphores or compute_config.create_semaphores()

    async def hydrate_context(self, ctx: WorkflowContext, db: AsyncSession):
        """
        Hydrates WorkflowContext from existing database artifacts when resuming.
        Issue #3: Queries are scoped by pipeline_run_id first, with fallback to content_id-only.
        """
        run_id = ctx.pipeline_run_id

        # 1. Research
        if not ctx.research:
            db_research = await self._find_artifact(
                db, DBResearch, ctx.content_id, run_id, "completed"
            )
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
            db_strategy = await self._find_artifact(
                db, DBStrategy, ctx.content_id, run_id, "completed"
            )
            if db_strategy:
                ctx.strategy = StrategyResult(
                    content_angle=db_strategy.content_angle or "Educational",
                    target_audience_analysis=db_strategy.target_audience_analysis or "General Audience",
                    hook_strategy=db_strategy.hook_strategy or "Curiosity Gap",
                    format_guidelines=db_strategy.format_guidelines or []
                )

        # 3. Script
        if not ctx.script:
            db_script = await self._find_artifact(
                db, DBScript, ctx.content_id, run_id, "completed"
            )
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
            sc_res = await self._find_artifacts_list(
                db, DBScene, ctx.content_id, run_id, "completed",
                order_by=DBScene.scene_number
            )
            if sc_res:
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
                    ) for sc in sc_res
                ])

        # 5. Scene Assets (strictly scoped to this pipeline run)
        db_scenes = await self._find_artifacts_list(
            db, DBScene, ctx.content_id, run_id, "completed",
            order_by=DBScene.scene_number
        )

        if run_id:
            a_res = await db.execute(
                select(DBAsset).filter(
                    DBAsset.content_id == ctx.content_id,
                    DBAsset.pipeline_run_id == run_id,
                    DBAsset.status == "completed"
                )
            )
            db_assets = a_res.scalars().all()
        else:
            # Legacy fallback — only when content has no pipeline_run_id
            a_res = await db.execute(
                select(DBAsset).filter(
                    DBAsset.content_id == ctx.content_id,
                    DBAsset.status == "completed"
                )
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

    async def _find_artifact(self, db, model_cls, content_id, run_id, status):
        """
        Find a single artifact scoped strictly to pipeline_run_id.

        Isolation contract:
        - When run_id is provided: query is STRICTLY scoped to that run only.
          No cross-run fallback. Run B can never see Run A's artifacts.
        - When run_id is None: legacy content (pre-dates pipeline_run_id); fall
          back to content_id-only query so old data remains readable.
        """
        if run_id:
            result = await db.execute(
                select(model_cls).filter(
                    model_cls.content_id == content_id,
                    model_cls.pipeline_run_id == run_id,
                    model_cls.status == status,
                ).order_by(model_cls.created_at.desc())
            )
            return result.scalars().first()

        # Legacy fallback — only reached when run_id is None (no pipeline_run_id column value)
        result = await db.execute(
            select(model_cls).filter(
                model_cls.content_id == content_id,
                model_cls.status == status,
            ).order_by(model_cls.created_at.desc())
        )
        return result.scalars().first()

    async def _find_artifacts_list(self, db, model_cls, content_id, run_id, status, order_by=None):
        """
        Find multiple artifacts scoped strictly to pipeline_run_id.

        Isolation contract:
        - When run_id is provided: STRICTLY scoped — no cross-run fallback.
        - When run_id is None: legacy content fallback to content_id-only.
        """
        order = order_by if order_by is not None else model_cls.created_at.desc()

        if run_id:
            result = await db.execute(
                select(model_cls).filter(
                    model_cls.content_id == content_id,
                    model_cls.pipeline_run_id == run_id,
                    model_cls.status == status,
                ).order_by(order)
            )
            return result.scalars().all()

        # Legacy fallback — only reached when run_id is None
        result = await db.execute(
            select(model_cls).filter(
                model_cls.content_id == content_id,
                model_cls.status == status,
            ).order_by(order)
        )
        return result.scalars().all()

    async def run(
        self,
        content_id: uuid.UUID,
        db: AsyncSession,
        model_overrides: Optional[Dict[str, str]] = None,
        resume: bool = True,
        pipeline_run_id: Optional[uuid.UUID] = None,
        raise_on_failure: bool = True,
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
        if content.metadata_json:
            ctx.strategy_dna = content.metadata_json
            if ctx.strategy_dna.get("target_audience"):
                ctx.target_audience = ctx.strategy_dna["target_audience"]

        # Issue #2: Distinguish start_new_run vs resume_run
        if resume and pipeline_run_id:
            # RESUME path: try to load existing PipelineRun
            existing_run = await db.execute(
                select(DBPipelineRun).filter(DBPipelineRun.id == run_id)
            )
            pipeline_run = existing_run.scalars().first()
            if pipeline_run:
                # Reuse existing run — set status back to running
                pipeline_run.status = "running"
                pipeline_run.current_stage = "RESUMING"
                pipeline_run.error = None
                await db.commit()
                await log_manager.broadcast(
                    f"🔄 Resuming PipelineRun {run_id} for '{ctx.title}'",
                    agent="ContentPipeline"
                )
            else:
                # pipeline_run_id provided but not found — create new
                pipeline_run = DBPipelineRun(
                    id=run_id,
                    content_id=content_id,
                    status="running",
                    current_stage="INIT",
                    model_overrides=model_overrides or {}
                )
                db.add(pipeline_run)
                await db.commit()
        else:
            # NEW path: reuse pre-created PipelineRun if present, otherwise insert
            existing_run = await db.get(DBPipelineRun, run_id) if run_id else None
            if existing_run:
                pipeline_run = existing_run
                pipeline_run.status = "running"
                pipeline_run.current_stage = "INIT"
                pipeline_run.error = None
                if model_overrides:
                    pipeline_run.model_overrides = model_overrides
                await db.commit()
            else:
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

                # Check final video asset — strictly scoped to this pipeline run
                if run_id:
                    a_res = await db.execute(
                        select(DBAsset).filter(
                            DBAsset.content_id == content_id,
                            DBAsset.pipeline_run_id == run_id,
                            DBAsset.asset_type == "video",
                            DBAsset.status == "completed",
                        )
                    )
                else:
                    a_res = await db.execute(
                        select(DBAsset).filter(
                            DBAsset.content_id == content_id,
                            DBAsset.asset_type == "video",
                            DBAsset.status == "completed",
                        )
                    )
                db_assets = a_res.scalars().all()
                vid_asset = next(
                    (a for a in db_assets
                     if os.path.exists(a.path) and os.path.getsize(a.path) > 1000),
                    None
                )
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

            # Mark this run as completed and current
            await db.execute(
                update(DBPipelineRun)
                .where(DBPipelineRun.content_id == content_id, DBPipelineRun.id != pipeline_run.id)
                .values(is_current=False)
            )
            pipeline_run.status = "completed"
            pipeline_run.is_current = True
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
            pipeline_run.is_current = False
            await db.commit()

            await update_workflow_state(db, content_id, WorkflowState.FAILED)
            await log_manager.broadcast(
                f"❌ Pipeline failed: {str(e)}",
                agent="ContentPipeline"
            )
            if raise_on_failure:
                raise
        finally:
            try:
                await self.model_manager.release_idle()
            except Exception as ex:
                logger.warning(f"Error releasing idle models after pipeline run: {ex}")

        return ctx

    @retry_async(max_attempts=2, delay=1.0)
    async def _run_research_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.RESEARCH)
        ctx.current_state = WorkflowState.RESEARCH
        
        research_model = self.model_router.route("research", ctx.model_overrides)
        await self.model_manager.ensure_loaded(research_model)
        agent = ResearchAgent(model=research_model)
        
        async with self.semaphores.research:
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

        strategy_model = self.model_router.route("strategy", ctx.model_overrides)
        await self.model_manager.ensure_loaded(strategy_model)
        agent = StrategyAgent(model=strategy_model)

        research_dict = ctx.research.model_dump() if ctx.research else {}
        async with self.semaphores.llm:
            async with AgentTracker(db, ctx.content_id, "STRATEGY", "StrategyAgent", provider=compute_config.llm.provider, model=strategy_model, pipeline_run_id=ctx.pipeline_run_id):
                strategy_res = await agent.develop_strategy(
                    topic=ctx.title,
                    research_data=research_dict,
                    platform=ctx.platform,
                    strategy_dna=ctx.strategy_dna,
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
        
        script_model = self.model_router.route("script", ctx.model_overrides)
        await self.model_manager.ensure_loaded(script_model)
        agent = ScriptAgent(model=script_model)
        
        research_dict = ctx.research.model_dump() if ctx.research else {}
        async with self.semaphores.llm:
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
        
        scene_model = self.model_router.route("scene", ctx.model_overrides)
        await self.model_manager.ensure_loaded(scene_model)
        agent = SceneAgent(model=scene_model)
        
        script_dict = ctx.script.model_dump() if ctx.script else {}
        async with self.semaphores.llm:
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

        image_model = self.model_router.route("image", ctx.model_overrides)
        await self.model_manager.ensure_loaded(image_model)
        voice_model = self.model_router.route("voice", ctx.model_overrides)
        await self.model_manager.ensure_loaded(voice_model)

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

        from app.services.visual_dna_service import VisualDNAService
        from app.services.broll_service import BRollService
        from app.services.auto_reframe import AutoReframeService

        broll_service = BRollService()
        style_pack_name = ctx.strategy_dna.get("visual_style_pack") or "dark_tech_cyberpunk"

        async def _process_scene_assets(scene_num: int, scene_db_id: uuid.UUID, prompt: str, narration: str, scene_dur: float):
            # Check B-roll anti-repetition matching
            should_broll, broll_clip = broll_service.should_use_broll(prompt)
            if should_broll and broll_clip:
                ctx.broll_assets[scene_num] = broll_clip.id

            # Enhance visual prompt with Visual DNA consistent styling
            dna_result = VisualDNAService.decorate_prompt(prompt, style_pack_name=style_pack_name)
            enhanced_prompt = dna_result.get("positive_prompt", prompt)

            # Check existing image asset
            existing_img = next((a for a in existing_assets if a.scene_id == scene_db_id and a.asset_type == "image" and os.path.exists(a.path) and os.path.getsize(a.path) > 100), None)
            if existing_img:
                img_path = existing_img.path
            else:
                async with self.semaphores.image_gpu:
                    async with AgentTracker(db, ctx.content_id, "ASSETS_IMAGE", "ImageAgent", provider=compute_config.image.provider, model=compute_config.image.model, pipeline_run_id=ctx.pipeline_run_id):
                        img_path = await image_agent.generate_image(prompt=enhanced_prompt)
                        # Ensure vertical saliency framing
                        if img_path and os.path.exists(img_path):
                            try:
                                AutoReframeService.reframe_image(img_path, img_path, target_resolution=(1080, 1920))
                            except Exception:
                                pass
            
            # Check existing audio asset
            existing_aud = next((a for a in existing_assets if a.scene_id == scene_db_id and a.asset_type == "audio" and os.path.exists(a.path) and os.path.getsize(a.path) > 100), None)
            if existing_aud:
                audio_path = existing_aud.path
                actual_duration = existing_aud.duration or scene_dur
            else:
                async with self.semaphores.tts:
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
        media_results = await asyncio.gather(*tasks, return_exceptions=True)

        first_error = None
        for res in media_results:
            if isinstance(res, Exception):
                if not first_error:
                    first_error = res
                continue

            scene_num, scene_db_id, prompt, img_path, audio_path, actual_duration, had_img, had_aud = res
            ctx.scene_assets[scene_num] = {}

            if not had_img and img_path:
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

            if not had_aud and audio_path:
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

            scene_record = next((sc for sc in db_scenes if sc.scene_number == scene_num), None)
            ctx.scene_assets[scene_num] = {
                "scene_id": scene_db_id,
                "duration": actual_duration,
                "onscreen_text": scene_record.onscreen_text if scene_record else None,
                "narration": scene_record.narration if scene_record else None,
                "image_path": img_path,
                "audio_path": audio_path
            }

        await db.commit()

        if first_error:
            raise first_error

    async def _run_render_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.RENDER)
        ctx.current_state = WorkflowState.RENDER
        
        video_model = self.model_router.route("video", ctx.model_overrides)
        await self.model_manager.ensure_loaded(video_model)

        video_agent = VideoAgent()
        scene_video_paths = []

        sorted_scenes = sorted(ctx.scene_assets.keys())
        async with self.semaphores.ffmpeg:
            async with AgentTracker(db, ctx.content_id, "RENDER", "VideoAgent", provider="ffmpeg", model="local-h264", pipeline_run_id=ctx.pipeline_run_id):
                for sc_num in sorted_scenes:
                    data = ctx.scene_assets[sc_num]
                    img_path = data["image_path"]
                    audio_path = data["audio_path"]
                    display_text = data.get("onscreen_text") or data.get("narration")
                    duration = data.get("duration", 5.0)

                    scene_vid = await video_agent.assemble_scene(
                        image_path=img_path,
                        audio_path=audio_path,
                        text=display_text,
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

        # Generate 3-way platform-aware thumbnail candidates using verified evidence
        try:
            from app.services.thumbnail_generator import ThumbnailGeneratorService
            thumb_gen = ThumbnailGeneratorService()
            first_scene_img = None
            for sc_n in sorted_scenes:
                candidate_img = ctx.scene_assets.get(sc_n, {}).get("image_path")
                if candidate_img and os.path.exists(candidate_img):
                    first_scene_img = candidate_img
                    break

            if first_scene_img:
                verified_stat = None
                findings = []
                if ctx.research:
                    findings = getattr(ctx.research, "statistics", []) or getattr(ctx.research, "key_points", [])
                for finding in findings:
                    if any(c.isdigit() for c in finding) and len(finding) < 40:
                        verified_stat = finding
                        break
                if not verified_stat and ctx.strategy and getattr(ctx.strategy, "hook", None):
                    hook = ctx.strategy.hook
                    if any(c.isdigit() for c in hook) and len(hook) < 30:
                        verified_stat = hook

                target_res = (1280, 720) if ctx.platform and ctx.platform.lower() == "youtube" else (1080, 1920)
                candidates = thumb_gen.generate_3way_thumbnails(
                    base_image_path=first_scene_img,
                    headline=ctx.title,
                    verified_statistic=verified_stat,
                    target_resolution=target_res,
                )
                ctx.thumbnails = [c.model_dump() for c in candidates]
                if candidates:
                    thumb_asset = DBAsset(
                        content_id=ctx.content_id,
                        pipeline_run_id=ctx.pipeline_run_id,
                        asset_type="thumbnail",
                        path=candidates[0].image_path,
                        filename=os.path.basename(candidates[0].image_path),
                        mime_type="image/jpeg",
                        provider="pillow-generator",
                        model="vidiq-3way",
                        status="completed",
                    )
                    db.add(thumb_asset)
                    await db.commit()
        except Exception as thumb_err:
            logger.warning(f"Thumbnail generation warning in pipeline: {thumb_err}")

    async def _run_quality_step(self, ctx: WorkflowContext, db: AsyncSession):
        await update_workflow_state(db, ctx.content_id, WorkflowState.QUALITY_CHECK)
        ctx.current_state = WorkflowState.QUALITY_CHECK

        async with self.semaphores.qa:
            async with AgentTracker(db, ctx.content_id, "QUALITY_CHECK", "QualityAgent", provider="internal", model="evaluator-v1", pipeline_run_id=ctx.pipeline_run_id):
                quality_res = await self.quality_agent.evaluate(
                    script=ctx.script,
                    scene_plan=ctx.scene_plan,
                    scene_assets=ctx.scene_assets,
                    final_video_path=ctx.final_video_path,
                )
        ctx.quality_result = quality_res
        if not quality_res.passed:
            err_reasons = ", ".join(quality_res.feedback) if quality_res.feedback else f"overall score {quality_res.overall_score}"
            raise RuntimeError(f"Quality check rejected render: {err_reasons}")


