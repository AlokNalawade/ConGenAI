import os
import json
import asyncio
import logging
import shutil
import re
from typing import Optional, Dict, Any
from app.models.ai_contracts import QualityResult, ScriptResult, ScenePlan

logger = logging.getLogger(__name__)

async def run_ffprobe_inspection(file_path: str, allow_fallback: Optional[bool] = None) -> Dict[str, Any]:
    """
    Executes ffprobe (or bundled ffmpeg inspection) to extract technical video/audio metadata.
    Fail-closed: if inspection tools are unavailable or fail, technical QA is rejected
    unless ALLOW_QA_FALLBACK is explicitly enabled for development.
    """
    if not file_path or not os.path.exists(file_path):
        return {"valid": False, "error": "File does not exist"}

    from app.core.config import settings
    fallback_enabled = allow_fallback if allow_fallback is not None else settings.ALLOW_QA_FALLBACK

    # 1. Try ffprobe if available
    ffprobe_bin = shutil.which("ffprobe")
    if ffprobe_bin:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                data = json.loads(stdout.decode())
                streams = data.get("streams", [])
                format_info = data.get("format", {})

                has_video = any(s.get("codec_type") == "video" for s in streams)
                has_audio = any(s.get("codec_type") == "audio" for s in streams)
                duration = float(format_info.get("duration", 0.0))
                size = int(format_info.get("size", 0))

                v_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
                width = int(v_stream.get("width", 0))
                height = int(v_stream.get("height", 0))

                return {
                    "valid": has_video,
                    "has_video": has_video,
                    "has_audio": has_audio,
                    "duration": duration,
                    "size": size,
                    "width": width,
                    "height": height,
                    "format": format_info.get("format_name"),
                    "streams_count": len(streams),
                    "is_fallback": False,
                }
        except Exception as ex:
            logger.warning(f"FFprobe execution error: {ex}")

    # 2. Try bundled FFmpeg inspection (-i metadata) if ffprobe was absent
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = None

    if ffmpeg_bin:
        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_bin,
                "-i",
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            out = stderr.decode()
            has_video = "Video:" in out
            has_audio = "Audio:" in out
            dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", out)
            duration = 0.0
            if dur_m:
                duration = int(dur_m.group(1)) * 3600 + int(dur_m.group(2)) * 60 + float(dur_m.group(3))
            res_m = re.search(r"Video:.*?(\d{3,4})x(\d{3,4})", out)
            width = int(res_m.group(1)) if res_m else 0
            height = int(res_m.group(2)) if res_m else 0
            size = os.path.getsize(file_path)

            if has_video:
                return {
                    "valid": True,
                    "has_video": True,
                    "has_audio": has_audio,
                    "duration": duration,
                    "size": size,
                    "width": width,
                    "height": height,
                    "format": "mp4",
                    "streams_count": (1 if has_video else 0) + (1 if has_audio else 0),
                    "is_fallback": False,
                }
        except Exception as e:
            logger.warning(f"FFmpeg inspection error: {e}")

    # 3. Fail-closed or dev fallback
    if not fallback_enabled:
        return {
            "valid": False,
            "error": "FFprobe and FFmpeg inspection unavailable or failed. Technical QA rejected."
        }
    logger.warning("ALLOW_QA_FALLBACK=True: using dev-only inspection fallback.")
    size = os.path.getsize(file_path)
    return {
        "valid": size > 1000,
        "has_video": True,
        "has_audio": True,
        "duration": 0.0,
        "size": size,
        "width": 1080,
        "height": 1920,
        "format": "mp4",
        "streams_count": 2,
        "is_fallback": True,
    }

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

        # 1. Script Quality Evaluation
        script_score = 0.0
        if script:
            script_score = 40.0
            if script.hook and len(script.hook.strip()) > 5:
                script_score += 20.0
            else:
                feedback.append("Script hook is weak or missing.")
                suggestions.append("Ensure the hook grabs attention in the first 3 seconds.")

            if script.body and len(script.body.strip()) > 20:
                script_score += 20.0
            else:
                feedback.append("Script body is too brief.")

            if script.cta and len(script.cta.strip()) > 3:
                script_score += 20.0
            else:
                suggestions.append("Add a clearer Call to Action at the end.")
        else:
            feedback.append("No script data found.")

        # 2. Audio Quality & Coverage Evaluation
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

        # 3. Technical Video Quality Evaluation (FFprobe)
        video_score = 0.0
        tech_info = {}
        if final_video_path and os.path.exists(final_video_path):
            tech_info = await run_ffprobe_inspection(final_video_path)
            if tech_info.get("valid"):
                video_score = 60.0
                if tech_info.get("has_video"):
                    video_score += 20.0
                if tech_info.get("has_audio"):
                    video_score += 20.0
                if tech_info.get("width", 0) > 0 and tech_info.get("height", 0) > 0:
                    video_score = min(100.0, video_score + 10.0)
            else:
                feedback.append(f"Technical video validation failed: {tech_info.get('error', 'corrupt file')}")
                suggestions.append("Re-render video using clean H.264 settings.")
        else:
            feedback.append("Final video file missing or non-existent.")

        # Fail-closed overall evaluation logic
        overall = round((script_score * 0.30) + (audio_score * 0.35) + (video_score * 0.35), 1)
        passed = (overall >= 60.0) and (video_score >= 60.0) and (audio_score >= 50.0)

        return QualityResult(
            overall_score=overall,
            script_score=script_score,
            audio_score=audio_score,
            video_score=video_score,
            passed=passed,
            feedback=feedback,
            suggestions=suggestions
        )
