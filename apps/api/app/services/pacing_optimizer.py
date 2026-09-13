"""Pacing & Retention Optimizer Service (CapCut style).

Implements hyper-engaging retention techniques:
1. Dead-Air Silence Stripper: Trims pauses in TTS narration longer than 250ms using FFmpeg.
2. 3-Second Punch-In Attention Reset: Alternates framing scale (1.0x to 1.12x) every 3 seconds
   to prevent viewer habituation and eye-fixation drop-off.
"""

from typing import Dict, Any


class PacingOptimizerService:
    @staticmethod
    def get_silence_removal_filter(
        min_silence_duration: float = 0.25,
        silence_threshold_db: str = "-35dB",
    ) -> str:
        """Construct FFmpeg audio filter string for silence stripping."""
        return (
            f"silenceremove=start_periods=1:start_duration=0.08:start_threshold={silence_threshold_db}:"
            f"stop_periods=-1:stop_duration={min_silence_duration}:stop_threshold={silence_threshold_db}"
        )

    @staticmethod
    def get_punch_in_zoom_filter(
        interval_seconds: float = 3.0,
        zoom_factor: float = 1.12,
        width: int = 1080,
        height: int = 1920,
        fps: int = 25,
    ) -> str:
        """Construct FFmpeg zoompan filter that alternates between normal scale and 1.12x punch-in every 3 seconds."""
        cycle = interval_seconds * 2  # e.g., 6 second total cycle (3s normal, 3s zoomed)
        # In zoompan: z expression checks whether mod(it, cycle) is in the second half of the cycle
        z_expr = f"if(between(mod(it,{cycle}),{interval_seconds},{cycle}),{zoom_factor},1.0)"
        return (
            f"zoompan=z='{z_expr}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={width}x{height}:fps={fps}"
        )
