import os
import logging
import httpx
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from app.services.providers.base import BaseImageProvider

logger = logging.getLogger(__name__)

class MockImageProvider(BaseImageProvider):
    async def generate_image(
        self,
        prompt: str,
        width: int = 1080,
        height: int = 1920,
        output_path: Optional[str] = None
    ) -> str:
        if not output_path:
            output_path = f"data/assets/images/mock_{os.urandom(4).hex()}.png"

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        img = Image.new('RGB', (width, height), color=(20, 24, 38))
        draw = ImageDraw.Draw(img)

        # Draw visual prompt placeholder text
        label = f"ConGen AI Scene Image\nPrompt: {prompt[:60]}..."
        try:
            font = ImageFont.load_default()
            draw.text((width // 10, height // 2), label, fill=(162, 155, 254), font=font)
        except Exception:
            draw.text((50, height // 2), label, fill=(255, 255, 255))

        img.save(output_path)
        logger.info(f"Generated mock image at {output_path}")
        return output_path

class ComfyUIProvider(BaseImageProvider):
    def __init__(self, server_url: str = "http://127.0.0.1:8188"):
        self.server_url = server_url

    async def generate_image(
        self,
        prompt: str,
        width: int = 1080,
        height: int = 1920,
        output_path: Optional[str] = None
    ) -> str:
        if not output_path:
            output_path = f"data/assets/images/comfy_{os.urandom(4).hex()}.png"

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Simple ComfyUI prompt API format
        workflow = {
            "3": {
                "inputs": {
                    "seed": 42,
                    "steps": 20,
                    "cfg": 7.0,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                },
                "class_type": "KSampler"
            },
            "4": {"inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"}, "class_type": "CheckpointLoaderSimple"},
            "5": {"inputs": {"width": width, "height": height, "batch_size": 1}, "class_type": "EmptyLatentImage"},
            "6": {"inputs": {"text": prompt}, "class_type": "CLIPTextEncode"},
            "7": {"inputs": {"text": "blurry, low quality, distorted"}, "class_type": "CLIPTextEncode"},
            "8": {"inputs": {"samples": ["3", 0], "vae": ["4", 2]}, "class_type": "VAEDecode"},
            "9": {"inputs": {"filename_prefix": "ConGen", "images": ["8", 0]}, "class_type": "SaveImage"}
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(f"{self.server_url}/prompt", json={"prompt": workflow})
                resp.raise_for_status()
                logger.info(f"ComfyUI job submitted successfully for prompt: {prompt[:30]}")
        except Exception as e:
            logger.warning(f"ComfyUI generation failed ({e}), falling back to MockImageProvider")
            mock = MockImageProvider()
            return await mock.generate_image(prompt, width, height, output_path)

        return output_path

class FluxProvider(BaseImageProvider):
    async def generate_image(
        self,
        prompt: str,
        width: int = 1080,
        height: int = 1920,
        output_path: Optional[str] = None
    ) -> str:
        # Placeholder fallback for local/cloud Flux API
        logger.info("FluxProvider invoked")
        mock = MockImageProvider()
        return await mock.generate_image(prompt, width, height, output_path)
