"""Kinetic Subtitle & Micro-SFX Injection Service (Submagic / Captions.ai style).

Transforms plain subtitles into high-retention kinetic captions:
- Injects dynamic emojis above or next to high-impact keywords (e.g., 💸 for money, 🔥 for growth, ⚠️ for risk)
- Generates synchronized sound effect (SFX) cue points (whoosh, pop, ding, cash) at exact word timestamps
"""

import os
import re
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from app.services.subtitle_service import SubtitleService
from app.core.config import settings


# Semantic dictionary mapping keyword roots to emojis and sound effects
KEYWORD_EMOJI_MAP: Dict[str, str] = {
    "money": "💸", "dollar": "💵", "profit": "📈", "revenue": "💰", "cash": "💸", "cost": "💳",
    "fire": "🔥", "insane": "🤯", "growth": "🚀", "scale": "🚀", "massive": "💥",
    "crash": "📉", "fail": "❌", "broken": "🛠️", "died": "☠️", "error": "⚠️", "bug": "🐛",
    "secret": "🤫", "hidden": "🔍", "truth": "💡", "reality": "👁️", "proven": "✅",
    "warning": "⚠️", "danger": "🚨", "stop": "🛑", "risk": "⚠️", "avoid": "⛔",
    "fast": "⚡", "speed": "⚡", "quick": "⏱️", "instant": "⚡", "boost": "🚀",
    "brain": "🧠", "smart": "🧠", "ai": "🤖", "agent": "🤖", "model": "🧬",
    "code": "💻", "dev": "👨‍💻", "engineer": "⚙️", "build": "🔨", "deploy": "🚢",
}

KEYWORD_SFX_MAP: Dict[str, str] = {
    "💸": "cash",
    "🔥": "whoosh",
    "📉": "glitch",
    "⚠️": "warning_ding",
    "⚡": "whoosh_fast",
    "🧠": "pop",
    "🚀": "riser",
    "✅": "ding",
}


class SoundCue(BaseModel):
    sfx_name: str
    timestamp: float
    volume: float = 0.8
    triggered_by_word: str


class KineticSubtitleResult(BaseModel):
    ass_file_path: str
    sfx_cues: List[SoundCue] = Field(default_factory=list)
    injected_emoji_count: int = 0


class KineticSubtitleService:
    @staticmethod
    def detect_keyword_emoji(word: str) -> Optional[str]:
        """Check if a word contains a trigger keyword root and return the corresponding emoji."""
        clean = re.sub(r"[^\w]", "", word.lower())
        for keyword, emoji in KEYWORD_EMOJI_MAP.items():
            if keyword in clean:
                return emoji
        return None

    @classmethod
    def generate_kinetic_ass(
        cls,
        text: str,
        duration: float,
        output_path: str,
        highlight_color: str = "&H0000FFFF",  # Bright Yellow
        main_color: str = "&H00FFFFFF",       # Pure White
    ) -> KineticSubtitleResult:
        """Generate styled ASS subtitle file with dynamic keyword emojis and return audio SFX cues."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        words = text.split()
        if not words:
            return KineticSubtitleResult(ass_file_path=output_path)

        time_per_word = duration / len(words)
        sfx_cues: List[SoundCue] = []
        injected_emoji_count = 0

        ass_header = f"""[Script Info]
Title: ConGen Kinetic Animated Subtitles
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Inter-Bold,52,{main_color},&H00000000,&H00000000,&H90000000,1,0,0,0,100,100,0,0,1,4,3,2,40,40,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        # Group words into 2-4 word rhythmic bursts (target 3 words per burst)
        burst_size = 3
        chunks = []
        for i in range(0, len(words), burst_size):
            chunks.append(words[i : i + burst_size])
        if len(chunks) > 1 and len(chunks[-1]) == 1:
            chunks[-2].extend(chunks.pop())

        def fmt_time(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            cs = int((seconds - int(seconds)) * 100)
            return f"{hrs:01d}:{mins:02d}:{secs:02d}.{cs:02d}"

        lines = []
        word_global_index = 0
        for chunk in chunks:
            for j, word in enumerate(chunk):
                start = word_global_index * time_per_word
                end = min(duration, (word_global_index + 1) * time_per_word)

                # Check for emoji injection
                emoji = cls.detect_keyword_emoji(word)
                if emoji:
                    injected_emoji_count += 1
                    sfx_name = KEYWORD_SFX_MAP.get(emoji, "pop")
                    sfx_cues.append(
                        SoundCue(
                            sfx_name=sfx_name,
                            timestamp=round(start, 2),
                            triggered_by_word=word,
                        )
                    )

                # Format the 2-4 word rhythmic burst with current word highlighted
                burst_display = []
                for k, w in enumerate(chunk):
                    w_emoji = cls.detect_keyword_emoji(w)
                    display_w = f"{w_emoji} {w}" if w_emoji else w
                    if k == j:
                        burst_display.append(f"{{\\c{highlight_color}}}{display_w}{{\\c{main_color}}}")
                    else:
                        burst_display.append(display_w)

                line_text = " ".join(burst_display)
                lines.append(f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},Default,,0,0,0,,{line_text}")
                word_global_index += 1

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(ass_header + "\n".join(lines))

        return KineticSubtitleResult(
            ass_file_path=output_path,
            sfx_cues=sfx_cues,
            injected_emoji_count=injected_emoji_count,
        )
