from app.services.image_service import ImageService
from app.core.logging import log_manager

class ImageAgent:
    def __init__(self):
        self.service = ImageService()
        
    async def generate(self, prompt: str, caption_text: str = None, width: int = 1080, height: int = 1920) -> str:
        await log_manager.broadcast(f"Generating scene image...", agent="ImageAgent")
        result = await self.service.generate_image(prompt, caption_text=caption_text, width=width, height=height)
        await log_manager.broadcast("Image generated successfully.", agent="ImageAgent")
        return result
