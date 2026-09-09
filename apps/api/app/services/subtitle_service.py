import os
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

class SubtitleService:
    @staticmethod
    def generate_ass_subtitle(
        text: str,
        duration: float,
        output_path: str,
        highlight_color: str = "&H0000FFFF",  # Yellow in ASS BGR format
        main_color: str = "&H00FFFFFF"        # White
    ) -> str:
        """
        Generates a styled ASS subtitle file with animated word highlighting for short-form video.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        words = text.split()
        if not words:
            return output_path

        time_per_word = duration / len(words)

        ass_header = f"""[Script Info]
Title: ConGen Animated Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter,48,{main_color},&H00000000,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,2,2,40,40,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        lines = []
        for i, word in enumerate(words):
            start = i * time_per_word
            end = min(duration, (i + 1) * time_per_word)
            
            def fmt_time(seconds: float) -> str:
                hrs = int(seconds // 3600)
                mins = int((seconds % 3600) // 60)
                secs = int(seconds % 60)
                cs = int((seconds - int(seconds)) * 100)
                return f"{hrs:01d}:{mins:02d}:{secs:02d}.{cs:02d}"

            # Format line with current word highlighted
            word_formatted = f"{{\\c{highlight_color}}}{word}{{\\c{main_color}}}"
            line_text = " ".join([w if idx != i else word_formatted for idx, w in enumerate(words)])
            lines.append(f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},Default,,0,0,0,,{line_text}")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(lines))

        logger.info(f"Generated ASS subtitle track at {output_path}")
        return output_path

    @staticmethod
    def burn_subtitles_ffmpeg(
        video_path: str,
        subtitle_path: str,
        output_path: str
    ) -> str:
        """
        Burns the ASS subtitle file directly onto the video using FFmpeg.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        # Escape path for FFmpeg filter argument
        escaped_sub = subtitle_path.replace("\\", "/").replace(":", "\\:")
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"subtitles='{escaped_sub}'",
            "-c:a", "copy",
            "-preset", "fast",
            output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            logger.info(f"Burned subtitles cleanly into video at {output_path}")
            return output_path
        except Exception as e:
            logger.warning(f"Failed to burn subtitles with FFmpeg ({e}), returning uncaptioned video")
            return video_path
