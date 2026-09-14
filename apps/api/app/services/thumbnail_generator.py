"""3-Way Mobile Thumbnail Candidate Generator (VidIQ / TubeBuddy style).

Generates 3 distinct high-converting mobile thumbnail variations for A/B testing:
1. Curiosity Hook: Giant bold yellow typography with heavy contrast shadow
2. High-Contrast Warning: Danger/warning pill badge + contrasting title
3. Statistic Proof: Large numerical metric callout + punchy takeaway
"""

import os
import uuid
from enum import Enum
from typing import List, Optional
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from app.core.config import settings


class ThumbnailStyle(str, Enum):
    CURIOSITY_HOOK = "curiosity_hook"
    WARNING_ALERT = "warning_alert"
    STATISTIC_PROOF = "statistic_proof"


class ThumbnailCandidate(BaseModel):
    id: str
    style: ThumbnailStyle
    image_path: str
    headline_text: str
    badge_text: Optional[str] = None


class ThumbnailGeneratorService:
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.join(settings.ASSETS_DIR, "thumbnails")
        os.makedirs(self.output_dir, exist_ok=True)

    def _draw_stroke_text(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple,
        text: str,
        fill: tuple = (255, 255, 255),
        stroke_fill: tuple = (0, 0, 0),
        stroke_width: int = 4,
    ):
        """Draw bold text with outline for mobile readability."""
        x, y = xy
        # Draw stroke offsets
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), text, fill=stroke_fill)
        # Draw main text
        draw.text((x, y), text, fill=fill)

    def generate_candidate(
        self,
        base_img: Image.Image,
        style: ThumbnailStyle,
        headline: str,
        badge: Optional[str] = None,
        target_resolution: tuple[int, int] = (1080, 1920),
    ) -> str:
        """Render an individual thumbnail candidate on canvas at specified platform resolution."""
        w, h = target_resolution
        canvas = base_img.copy().resize((w, h), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(canvas)

        # Style 1: Curiosity Hook (Yellow High Contrast)
        if style == ThumbnailStyle.CURIOSITY_HOOK:
            b_top = int(h * 0.05)
            b_bottom = int(h * 0.22)
            draw.rectangle([0, b_top, w, b_bottom], fill=(0, 0, 0, 200))
            self._draw_stroke_text(draw, (int(w * 0.07), b_top + int(h * 0.03)), headline[:35].upper(), fill=(255, 230, 0), stroke_fill=(0, 0, 0), stroke_width=6)
            if badge:
                draw.rounded_rectangle([int(w * 0.07), b_bottom - int(h * 0.05), int(w * 0.45), b_bottom - int(h * 0.01)], radius=15, fill=(255, 59, 48))
                draw.text((int(w * 0.09), b_bottom - int(h * 0.04)), badge.upper(), fill=(255, 255, 255))

        # Style 2: Warning Alert (Red & White Danger Pill)
        elif style == ThumbnailStyle.WARNING_ALERT:
            badge_text = badge or "⚠️ CRITICAL ALERT"
            draw.rounded_rectangle([int(w * 0.07), int(h * 0.06), int(w * 0.55), int(h * 0.11)], radius=20, fill=(255, 59, 48))
            draw.text((int(w * 0.10), int(h * 0.075)), badge_text, fill=(255, 255, 255))
            # Dark backing banner
            draw.rectangle([0, int(h * 0.12), w, int(h * 0.28)], fill=(15, 23, 42, 220))
            self._draw_stroke_text(draw, (int(w * 0.07), int(h * 0.15)), headline[:40].upper(), fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=6)

        # Style 3: Statistic Proof (Numerical Callout with Verified Evidence)
        elif style == ThumbnailStyle.STATISTIC_PROOF:
            stat_text = badge or "VERIFIED DATA"
            draw.rounded_rectangle([int(w * 0.07), int(h * 0.07), int(w * 0.55), int(h * 0.17)], radius=25, fill=(0, 184, 148))
            draw.text((int(w * 0.10), int(h * 0.095)), stat_text, fill=(0, 0, 0))
            # Headline under stat
            draw.rectangle([0, int(h * 0.19), w, int(h * 0.32)], fill=(0, 0, 0, 210))
            self._draw_stroke_text(draw, (int(w * 0.07), int(h * 0.22)), headline[:35].upper(), fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=5)

        res_suffix = f"{w}x{h}"
        out_name = f"thumb_{style.value}_{res_suffix}_{uuid.uuid4().hex[:6]}.jpg"
        out_path = os.path.join(self.output_dir, out_name)
        canvas.convert("RGB").save(out_path, "JPEG", quality=90)
        return out_path

    def generate_3way_thumbnails(
        self,
        base_image_path: str,
        headline: str,
        stat_or_warning: Optional[str] = None,
        verified_statistic: Optional[str] = None,
        target_resolution: tuple[int, int] = (1080, 1920),
    ) -> List[ThumbnailCandidate]:
        """Produce 3 distinct high-CTR thumbnail candidates using verified evidence and platform resolution."""
        img = Image.open(base_image_path)
        candidates = []

        # 1. Curiosity Hook
        c1_path = self.generate_candidate(img, ThumbnailStyle.CURIOSITY_HOOK, headline, badge="WATCH FIRST", target_resolution=target_resolution)
        candidates.append(
            ThumbnailCandidate(
                id=f"c_{uuid.uuid4().hex[:6]}",
                style=ThumbnailStyle.CURIOSITY_HOOK,
                image_path=c1_path,
                headline_text=headline,
                badge_text="WATCH FIRST",
            )
        )

        # 2. Warning Alert
        badge2 = stat_or_warning or "⚠️ CRITICAL ALERT"
        c2_path = self.generate_candidate(img, ThumbnailStyle.WARNING_ALERT, headline, badge=badge2, target_resolution=target_resolution)
        candidates.append(
            ThumbnailCandidate(
                id=f"c_{uuid.uuid4().hex[:6]}",
                style=ThumbnailStyle.WARNING_ALERT,
                image_path=c2_path,
                headline_text=headline,
                badge_text=badge2,
            )
        )

        # 3. Statistic Proof (only verified statistics from research/strategy or verified blueprint)
        badge3 = verified_statistic or (stat_or_warning if (stat_or_warning and any(c.isdigit() for c in stat_or_warning)) else "VERIFIED DATA")
        c3_path = self.generate_candidate(img, ThumbnailStyle.STATISTIC_PROOF, headline, badge=badge3, target_resolution=target_resolution)
        candidates.append(
            ThumbnailCandidate(
                id=f"c_{uuid.uuid4().hex[:6]}",
                style=ThumbnailStyle.STATISTIC_PROOF,
                image_path=c3_path,
                headline_text=headline,
                badge_text=badge3,
            )
        )

        return candidates
