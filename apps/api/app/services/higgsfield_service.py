import asyncio
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


class HiggsfieldVideoService:
    """Generate cloud video through the official Higgsfield Python SDK.

    Credentials stay server-side. The service downloads the completed asset
    into ConGenAI's local asset directory so downstream FFmpeg/QA stages can
    treat cloud output like any other video asset.
    """

    DEFAULT_MODEL = "minimax/h3/text-to-video"

    def __init__(self):
        self.model = os.getenv("HIGGSFIELD_VIDEO_MODEL", self.DEFAULT_MODEL)
        self.output_dir = Path(settings.ASSETS_DIR) / "videos" / "higgsfield"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _configure_credentials() -> None:
        # Support both the official SDK names and ConGenAI-specific names.
        # Never log these values.
        if not os.getenv("HF_KEY"):
            key_id = os.getenv("HIGGSFIELD_API_KEY_ID")
            key_secret = os.getenv("HIGGSFIELD_API_KEY_SECRET")
            if key_id and key_secret:
                os.environ["HF_KEY"] = f"{key_id}:{key_secret}"

    @staticmethod
    def _video_url(result: Any) -> str:
        video = result.get("video") if isinstance(result, dict) else None
        if isinstance(video, str):
            return video
        if isinstance(video, dict):
            for key in ("url", "uri", "download_url"):
                value = video.get(key)
                if value:
                    return value
        if isinstance(video, list) and video:
            first = video[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for key in ("url", "uri", "download_url"):
                    value = first.get(key)
                    if value:
                        return value
        raise RuntimeError("Higgsfield completed without a video URL")

    async def generate(
        self,
        prompt: str,
        duration: int = 5,
        resolution: str = "2K",
        aspect_ratio: str = "auto",
        aigc_watermark: bool = False,
    ) -> dict:
        if not prompt.strip():
            raise ValueError("Higgsfield prompt must not be empty")
        if duration < 5 or duration > 15:
            raise ValueError("Higgsfield H3 duration must be between 5 and 15 seconds")
        if resolution != "2K":
            raise ValueError("Higgsfield H3 currently supports 2K output")
        if aspect_ratio not in {"auto", "adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}:
            raise ValueError("Unsupported Higgsfield H3 aspect ratio")

        if not settings.ALLOW_EXTERNAL_GENERATION:
            raise PermissionError(
                "External generation is disabled. Set ALLOW_EXTERNAL_GENERATION=true "
                "only when you want ConGenAI to use Higgsfield."
            )

        self._configure_credentials()
        if not os.getenv("HF_KEY"):
            raise RuntimeError(
                "Higgsfield credentials are missing. Set HF_KEY or "
                "HIGGSFIELD_API_KEY_ID/HIGGSFIELD_API_KEY_SECRET."
            )

        try:
            import higgsfield_client
        except ImportError as exc:
            raise RuntimeError(
                "Higgsfield SDK is not installed. Run: pip install higgsfield-client"
            ) from exc

        result = await higgsfield_client.subscribe_async(
            self.model,
            arguments={
                "prompt": prompt,
                "duration": duration,
                "resolution": resolution,
                "aspect_ratio": aspect_ratio,
                "aigc_watermark": aigc_watermark,
            },
        )
        video_url = self._video_url(result)

        output = self.output_dir / f"higgsfield_{uuid.uuid4().hex}.mp4"
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            response = await client.get(video_url)
            response.raise_for_status()
            output.write_bytes(response.content)

        if output.stat().st_size == 0:
            raise RuntimeError("Higgsfield returned an empty video file")

        return {
            "path": str(output),
            "model": self.model,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "source_url": video_url,
        }
