from app.services.video_service import VideoService
from app.core.logging import log_manager
import asyncio

class VideoAgent:
    def __init__(self):
        self.service = VideoService()
        
    async def assemble_scene(self, image_path: str, audio_path: str, text: str = None) -> str:
        await log_manager.broadcast(f"Assembling scene video...", agent="VideoAgent")
        return await asyncio.to_thread(self.service.create_scene_video, image_path, audio_path, text)
        
    async def assemble_final(self, video_paths: list[str]) -> str:
        await log_manager.broadcast(f"Concatenating {len(video_paths)} scenes into final video...", agent="VideoAgent")
        result = await asyncio.to_thread(self.service.concatenate_videos, video_paths)
        await log_manager.broadcast("Final video assembly complete!", agent="VideoAgent")
        return result
