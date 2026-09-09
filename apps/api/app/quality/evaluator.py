import os
import logging
from typing import Optional
from app.models.ai_contracts import QualityResult, ScriptResult, ScenePlan

logger = logging.getLogger(__name__)

class QualityAgent:
    def __init__(self):
        pass

    async def evaluate(
        self,
        script: Optional[ScriptResult] = None,
        scene_plan: Optional[ScenePlan] = None,
        scene_assets: Optional[dict] = None,
        final_video_path: Optional[str] = None
    ) -> QualityResult:
        feedback = []
        suggestions = []

        # 1. Script Quality
        script_score = 0.0
        if script:
            script_score = 50.0 # Base score for existence
            if script.hook and len(script.hook.strip()) > 5:
                script_score += 15.0
            else:
                feedback.append("Script hook is weak or missing.")
                suggestions.append("Ensure the hook grabs attention in the first 3 seconds.")

            if script.body and len(script.body.strip()) > 20:
                script_score += 20.0
            else:
                feedback.append("Script body is too brief.")

            if script.cta and len(script.cta.strip()) > 3:
                script_score += 15.0
            else:
                suggestions.append("Add a clearer Call to Action at the end.")
        else:
            feedback.append("No script data found.")

        # 2. Audio Quality & Scene Coverage
        audio_score = 0.0
        total_scenes = len(scene_plan.scenes) if scene_plan and scene_plan.scenes else 0
        audio_count = 0

        if scene_assets and total_scenes > 0:
            for scene_num, assets in scene_assets.items():
                audio_path = assets.get("audio_path")
                if audio_path and os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                    audio_count += 1
            
            coverage = audio_count / total_scenes
            audio_score = round(coverage * 100.0, 1)
            if audio_count < total_scenes:
                feedback.append(f"Audio missing for {total_scenes - audio_count} of {total_scenes} scenes.")
        elif total_scenes == 0:
            feedback.append("No planned scenes found for audio validation.")

        # 3. Video Quality
        video_score = 0.0
        image_count = 0
        if scene_assets and total_scenes > 0:
            for scene_num, assets in scene_assets.items():
                img_path = assets.get("image_path")
                if img_path and os.path.exists(img_path) and os.path.getsize(img_path) > 0:
                    image_count += 1

        if final_video_path and os.path.exists(final_video_path) and os.path.getsize(final_video_path) > 1000:
            video_score = 70.0
            if total_scenes > 0:
                img_coverage = image_count / total_scenes
                video_score += round(img_coverage * 30.0, 1)
        else:
            feedback.append("Final video file missing or corrupted.")
            suggestions.append("Check FFmpeg output logs for video render issues.")

        # Overall weighted score: Script (35%), Audio (30%), Video (35%)
        overall = round((script_score * 0.35) + (audio_score * 0.30) + (video_score * 0.35), 1)
        passed = overall >= 60.0

        return QualityResult(
            overall_score=overall,
            script_score=script_score,
            audio_score=audio_score,
            video_score=video_score,
            passed=passed,
            feedback=feedback,
            suggestions=suggestions
        )
