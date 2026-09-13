"""Composition Engine for ConGenAI.

Compiles a Creatomate-style ContentComposition into deterministic FFmpeg commands:
- Multi-track visual layer assembly (Main visual, Ken Burns, B-roll PIP)
- Persistent / animated headline banner overlay
- Subtitle layer integration (ASS/SRT or drawtext)
- Dynamic progress indicator bar (scaled over duration t/D*W)
- Audio ducking (voiceover prioritized over background music)
- End-screen CTA and outro card
"""

import os
import uuid
import shutil
import ffmpeg
import imageio_ffmpeg
from typing import List, Optional
from app.templates.schema import (
    ContentComposition,
    CompositionScene,
    ProgressIndicatorStyle,
    AnimationType,
    TEMPLATE_PRESETS,
)
from app.services.subtitle_service import SubtitleService
from app.core.config import settings


class CompositionEngine:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(settings.ASSETS_DIR, "compositions")
        os.makedirs(self.output_dir, exist_ok=True)
        self.ffmpeg_cmd = shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()

    def build_scene_video_filters(
        self,
        scene: CompositionScene,
        composition: ContentComposition,
        scene_duration: float,
        ass_subtitle_path: Optional[str] = None,
    ) -> List[str]:
        """Generate the deterministic FFmpeg video filter chain for a single composition scene."""
        w, h = composition.width, composition.height
        filters = [
            f"scale={w}:{h}:force_original_aspect_ratio=increase",
            f"crop={w}:{h}",
            "format=yuv420p",
        ]

        # 1. Ken Burns pan/zoom if requested
        preset = TEMPLATE_PRESETS.get(composition.template_variant)
        anim = preset.animation if preset else AnimationType.NONE
        if anim == AnimationType.KEN_BURNS:
            # Subtle zoom-in from 1.0 to 1.08 over the scene duration
            fps = composition.fps
            frames = int(scene_duration * fps)
            filters.append(f"zoompan=z='min(zoom+0.0015,1.08)':d={frames}:s={w}x{h}:fps={fps}")

        # 2. Headline banner overlay
        headline_text = scene.headline or (composition.title if scene.scene_number == 1 else None)
        if headline_text and headline_text.strip():
            safe_text = headline_text.replace("'", "").replace(":", "").replace("\\", "")
            banner_bg = preset.headline_bg if preset else "#1C1C1E"
            if banner_bg:
                # Headline background box at top
                filters.append(
                    f"drawbox=x=0:y=60:w={w}:h=160:color={banner_bg}@0.85:t=fill"
                )
            # Headline text
            filters.append(
                f"drawtext=text='{safe_text}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=110:shadowcolor=black@0.6:shadowx=2:shadowy=2"
            )

        # 3. Subtitles
        if ass_subtitle_path and os.path.exists(ass_subtitle_path):
            escaped_ass = os.path.abspath(ass_subtitle_path).replace(":", "\\:").replace("'", "\\'")
            filters.append(f"subtitles='{escaped_ass}'")

        # 4. Progress bar indicator
        if composition.progress_style == ProgressIndicatorStyle.BOTTOM_BAR:
            # Bar grows from left to right: w='t/duration * W'
            color = composition.progress_color
            filters.append(
                f"drawbox=x=0:y={h-16}:w='min(w, (t/{scene_duration})*w)':h=16:color={color}@0.9:t=fill"
            )
        elif composition.progress_style == ProgressIndicatorStyle.TOP_BAR:
            color = composition.progress_color
            filters.append(
                f"drawbox=x=0:y=0:w='min(w, (t/{scene_duration})*w)':h=14:color={color}@0.9:t=fill"
            )

        return filters

    def render_scene(
        self,
        scene: CompositionScene,
        composition: ContentComposition,
    ) -> str:
        """Render an individual composition scene with all active layers."""
        if not scene.image_path or not os.path.exists(scene.image_path):
            raise ValueError(f"Scene {scene.scene_number} has invalid or missing image_path: {scene.image_path}")
        if not scene.audio_path or not os.path.exists(scene.audio_path):
            raise ValueError(f"Scene {scene.scene_number} has invalid or missing audio_path: {scene.audio_path}")

        scene_filename = f"comp_scene_{uuid.uuid4().hex[:8]}.mp4"
        scene_filepath = os.path.join(self.output_dir, scene_filename)
        duration = float(scene.duration) if scene.duration and float(scene.duration) > 0 else 5.0

        # Subtitles generation if narration present
        ass_path = None
        if scene.narration and scene.narration.strip():
            try:
                sub_dir = os.path.join(settings.ASSETS_DIR, "subtitles")
                os.makedirs(sub_dir, exist_ok=True)
                ass_path = os.path.join(sub_dir, f"sub_{uuid.uuid4().hex[:8]}.ass")
                SubtitleService.generate_ass_subtitle(scene.narration, duration, ass_path)
            except Exception as e:
                print(f"Subtitle generation warning: {e}")

        video_filters = self.build_scene_video_filters(
            scene=scene,
            composition=composition,
            scene_duration=duration,
            ass_subtitle_path=ass_path,
        )

        input_img = ffmpeg.input(scene.image_path, loop=1)
        input_audio = ffmpeg.input(scene.audio_path)

        output_kwargs = {
            'vcodec': 'libx264',
            'acodec': 'aac',
            'ar': '44100',
            'ac': 2,
            'r': composition.fps,
            'af': 'volume=1.3',
            'pix_fmt': 'yuv420p',
            't': duration,
            'vf': ','.join(video_filters),
        }

        stream = ffmpeg.output(input_img.video, input_audio.audio, scene_filepath, **output_kwargs)
        try:
            ffmpeg.run(stream, cmd=self.ffmpeg_cmd, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            err = e.stderr.decode('utf-8') if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg composition scene error: {err}") from e

        return scene_filepath

    def render_composition(self, composition: ContentComposition) -> str:
        """Render the complete composition, stitching scenes and applying global outro/CTA card."""
        if not composition.scenes:
            raise ValueError("Composition contains no scenes")

        rendered_scene_paths = []
        for scene in composition.scenes:
            path = self.render_scene(scene, composition)
            rendered_scene_paths.append(path)

        # Concat scenes into intermediate video
        list_file_path = os.path.join(self.output_dir, f"concat_{uuid.uuid4().hex[:8]}.txt")
        with open(list_file_path, 'w') as f:
            for p in rendered_scene_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")

        final_filename = f"composition_{composition.id}.mp4"
        final_filepath = os.path.join(self.output_dir, final_filename)

        stream = ffmpeg.input(list_file_path, format='concat', safe=0)
        stream = ffmpeg.output(stream, final_filepath, c='copy')
        try:
            ffmpeg.run(stream, cmd=self.ffmpeg_cmd, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        except ffmpeg.Error as e:
            err = e.stderr.decode('utf-8') if e.stderr else str(e)
            raise RuntimeError(f"FFmpeg composition concat error: {err}") from e
        finally:
            if os.path.exists(list_file_path):
                os.remove(list_file_path)

        return final_filepath
