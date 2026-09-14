import os
import uuid
import asyncio
import textwrap
import urllib.request
import urllib.parse
import re
import random
from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings

def clean_text(text: str) -> str:
    if not text:
        return ''
    # Strip meta prefixes like "A prompt for...", "Image prompt of...", "Scene 1: Visual of..."
    text = re.sub(r'^scene\s*\d*:?\s*', '', text, flags=re.I)
    text = re.sub(r'^(a\s+)?(visual\s+)?(description|prompt|image|photo|picture)\s*(for|of)?:\s*', '', text, flags=re.I)
    text = re.sub(r'^(a\s+prompt\s+(for|of)|image\s+prompt\s+(for|of)|a\s+visual\s+description\s+(for|of)|a\s+photo\s+of|a\s+picture\s+of|visual\s+of)\s+', '', text, flags=re.I)
    return text.strip()

class ImageService:
    def __init__(self):
        self.output_dir = os.path.join("data", "assets", "images")
        os.makedirs(self.output_dir, exist_ok=True)

    async def generate_image(self, prompt: str, caption_text: str = None, width: int = 1080, height: int = 1920) -> str:
        """
        Generates HD visual scene imagery (1080x1920) with clean subtitle overlays.
        When ALLOW_EXTERNAL_GENERATION is enabled, fetches from Pollinations/LoremFlickr/Picsum.
        By default (ALLOW_EXTERNAL_GENERATION=False), executes local-first high-contrast rendering.
        """
        cleaned_prompt = clean_text(prompt)
        cleaned_caption = clean_text(caption_text) if caption_text else cleaned_prompt
        
        print(f"Generating scene image | Cleaned Prompt: '{cleaned_prompt[:60]}...'")
        filename = f"{uuid.uuid4()}.jpg"
        filepath = os.path.join(self.output_dir, filename)
        
        img = None
        if getattr(settings, "ALLOW_EXTERNAL_GENERATION", False):
            seed = random.randint(100, 999999)
            first_word = (cleaned_prompt.split()[0] if cleaned_prompt else 'scene').lower()
            providers = [
                f"https://image.pollinations.ai/prompt/high%20quality%20vertical%20photo%20{urllib.parse.quote(cleaned_prompt[:150])}?width={width}&height={height}&nologo=true&seed={seed}",
                f"https://loremflickr.com/{width}/{height}/{urllib.parse.quote(first_word)}",
                f"https://picsum.photos/{width}/{height}?random={seed}"
            ]
            
            for url in providers:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    def _fetch(u=url):
                        with urllib.request.urlopen(req, timeout=6) as resp:
                            return Image.open(resp).convert('RGB')
                    img = await asyncio.to_thread(_fetch)
                    if img:
                        print(f"Scene visual fetched successfully from provider.")
                        break
                except Exception as e:
                    continue

        # Fallback to vibrant Pillow graphic if all external APIs are unreachable
        if img is None:
            img = Image.new('RGB', (width, height), color=(20, 22, 36))
            draw = ImageDraw.Draw(img)
            draw.rectangle([40, 40, width - 40, height - 40], outline=(108, 92, 231), width=8)
            card_box = [80, height//4, width - 80, 3*height//4]
            draw.rectangle(card_box, fill=(30, 32, 50), outline=(162, 155, 254), width=4)

        img = img.resize((width, height), Image.Resampling.LANCZOS)
        
        # Overlay TikTok / Shorts style caption backdrop
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)
        
        box_h = 260
        y_start = height - 380
        draw_ov.rounded_rectangle(
            [50, y_start, width - 50, y_start + box_h],
            radius=20,
            fill=(0, 0, 0, 195),
            outline=(255, 255, 255, 75),
            width=2
        )
        
        font_title = ImageFont.load_default(size=44)
        font_sub = ImageFont.load_default(size=30)
        
        wrapped_lines = textwrap.wrap(cleaned_caption, width=28)
        subtitle_str = "\n".join(wrapped_lines[:3])
        
        draw_ov.text((80, y_start + 30), subtitle_str, fill=(255, 255, 255, 255), font=font_title)
        draw_ov.text((80, y_start + box_h - 45), "⚡ ConGen AI Short", fill=(162, 155, 254, 255), font=font_sub)
        
        final_img = Image.alpha_composite(img.convert('RGBA'), overlay)
        final_img.convert('RGB').save(filepath, format='JPEG', quality=95)
        
        return filepath
