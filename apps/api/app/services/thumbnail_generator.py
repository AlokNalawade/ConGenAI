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
    ) -> str:
        """Render an individual thumbnail candidate on canvas."""
        canvas = base_img.copy().resize((1080, 1920), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(canvas)

        # Style 1: Curiosity Hook (Yellow High Contrast)
        if style == ThumbnailStyle.CURIOSITY_HOOK:
            # Top banner box
            draw.rectangle([0, 100, 1080, 420], fill=(0, 0, 0, 200))
            self._draw_stroke_text(draw, (80, 160), headline[:35].upper(), fill=(255, 230, 0), stroke_fill=(0, 0, 0), stroke_width=6)
            if badge:
                # Pill badge
                draw.rounded_rectangle([80, 320, 360, 390], radius=15, fill=(255, 59, 48))
                draw.text((100, 340), badge.upper(), fill=(255, 255, 255))

        # Style 2: Warning Alert (Red & White Danger Pill)
        elif style == ThumbnailStyle.WARNING_ALERT:
            # Pill badge at top
            draw.rounded_rectangle([80, 120, 420, 200], radius=20, fill=(255, 59, 48))
            draw.text((110, 145), badge or "⚠️ CRITICAL WARNING", fill=(255, 255, 255))
            # Dark backing banner
            draw.rectangle([0, 240, 1080, 520], fill=(15, 23, 42, 220))
            self._draw_stroke_text(draw, (80, 290), headline[:40].upper(), fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=6)

        # Style 3: Statistic Proof (Numerical Callout)
        elif style == ThumbnailStyle.STATISTIC_PROOF:
            # Giant stat box
            draw.rounded_rectangle([80, 140, 500, 320], radius=25, fill=(0, 184, 148))
            draw.text((110, 180), badge or "90% FAIL", fill=(0, 0, 0))
            # Headline under stat
            draw.rectangle([0, 360, 1080, 580], fill=(0, 0, 0, 210))
            self._draw_stroke_text(draw, (80, 410), headline[:35].upper(), fill=(255, 255, 255), stroke_fill=(0, 0, 0), stroke_width=5)

        out_name = f"thumb_{style.value}_{uuid.uuid4().hex[:6]}.jpg"
        out_path = os.path.join(self.output_dir, out_name)
        canvas.convert("RGB").save(out_path, "JPEG", quality=90)
        return out_path

    def generate_3way_thumbnails(
        self,
        base_image_path: str,
        headline: str,
        stat_or_warning: Optional[str] = None,
    ) -> List[ThumbnailCandidate]:
        """Produce 3 distinct high-CTR thumbnail candidates."""
        img = Image.open(base_image_path)
        candidates = []

        # 1. Curiosity Hook
        c1_path = self.generate_candidate(img, ThumbnailStyle.CURIOSITY_HOOK, headline, badge="WATCH FIRST")
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
        c2_path = self.generate_candidate(img, ThumbnailStyle.WARNING_ALERT, headline, badge=stat_or_warning or "⚠️ DO NOT DEPLOY")
        candidates.append(
            ThumbnailCandidate(
                id=f"c_{uuid.uuid4().hex[:6]}",
                style=ThumbnailStyle.WARNING_ALERT,
                image_path=c2_path,
                headline_text=headline,
                badge_text=stat_or_warning or "⚠️ DO NOT DEPLOY",
            )
        )

        # 3. Statistic Proof
        c3_path = self.generate_candidate(img, ThumbnailStyle.STATISTIC_PROOF, headline, badge="90% FAIL")
        candidates.append(
            ThumbnailCandidate(
                id=f"c_{uuid.uuid4().hex[:6]}",
                style=ThumbnailStyle.STATISTIC_PROOF,
                image_path=c3_path,
                headline_text=headline,
                badge_text="90% FAIL",
            )
        )

        return candidates
