"""Visual DNA & Style Consistency Locks (Runway style).

Enforces visual coherence across an entire video batch:
- Curated Visual Style Packs with locked prompt prefixes and negative suites
- Color palette anchors and texture descriptors
- Seed mode coordination so scenes in the same story share identical aesthetic DNA
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class VisualStylePack(BaseModel):
    name: str
    display_name: str
    description: str
    prompt_prefix: str
    prompt_suffix: str
    negative_prompt: str
    color_palette: List[str]
    default_seed: int = 42


STYLE_PACKS: Dict[str, VisualStylePack] = {
    "dark_tech_cyberpunk": VisualStylePack(
        name="dark_tech_cyberpunk",
        display_name="Dark Tech Cyberpunk",
        description="Moody volumetric lighting, dark slate background, emerald/cyan circuit accents, matte textures.",
        prompt_prefix="cinematic film still, dark slate atmosphere, glowing cyan and emerald terminal accents, high contrast,",
        prompt_suffix="octane render, 8k resolution, photorealistic, cinematic depth of field, sharp focus",
        negative_prompt="cartoon, 3d plastic render, oversaturated rainbow colors, distorted limbs, blurry background, watermark",
        color_palette=["#0b0f19", "#00cec9", "#00b894", "#1e293b"],
        default_seed=1337,
    ),
    "minimal_monochrome": VisualStylePack(
        name="minimal_monochrome",
        display_name="Minimalist Monochrome",
        description="Clean architectural minimalism, stark black & white contrast, geometric elegance.",
        prompt_prefix="minimalist architectural photography, clean studio monochrome, harsh clean shadows,",
        prompt_suffix="leica monochrome lens, fine art photography, clean negative space, 8k",
        negative_prompt="cluttered, vibrant color, neon, messy, low quality, artifacting, blur",
        color_palette=["#000000", "#ffffff", "#718096"],
        default_seed=2026,
    ),
    "retro_analog_35mm": VisualStylePack(
        name="retro_analog_35mm",
        display_name="Retro Analog 35mm",
        description="Warm Kodachrome film grain, tungsten light flares, nostalgic documentary look.",
        prompt_prefix="35mm analog photograph, kodak portra 400 grain, warm nostalgic tungsten lighting,",
        prompt_suffix="natural film texture, anamorphic lens flare, authentic archival documentary style",
        negative_prompt="digital cgi, plastic render, sharp vector, oversaturated, modern digital look",
        color_palette=["#2c1810", "#d4a373", "#faedcd"],
        default_seed=1984,
    ),
    "corporate_vector_25d": VisualStylePack(
        name="corporate_vector_25d",
        display_name="Corporate Vector 2.5D",
        description="Polished isometric tech infographics, clean drop shadows, enterprise SaaS aesthetic.",
        prompt_prefix="isometric 2.5d clean tech illustration, crisp vector lines, subtle soft gradients,",
        prompt_suffix="dribbble trending, behance feature, polished enterprise product design aesthetic",
        negative_prompt="photorealistic, messy, grunge, noise, human faces, grainy, low resolution",
        color_palette=["#4f46e5", "#06b6d4", "#f8fafc"],
        default_seed=5000,
    ),
}


class VisualDNAService:
    @staticmethod
    def get_style_pack(pack_name: str) -> VisualStylePack:
        """Retrieve style pack by name, with fallback to dark_tech_cyberpunk."""
        return STYLE_PACKS.get(pack_name, STYLE_PACKS["dark_tech_cyberpunk"])

    @classmethod
    def decorate_prompt(
        cls,
        base_prompt: str,
        style_pack_name: str = "dark_tech_cyberpunk",
        custom_negative: Optional[str] = None,
    ) -> Dict[str, str]:
        """Wrap base scene prompt with style pack prefixes and negative prompt locks."""
        pack = cls.get_style_pack(style_pack_name)
        full_positive = f"{pack.prompt_prefix} {base_prompt}, {pack.prompt_suffix}".strip()
        
        full_negative = pack.negative_prompt
        if custom_negative:
            full_negative = f"{full_negative}, {custom_negative}"

        return {
            "positive_prompt": full_positive,
            "negative_prompt": full_negative,
            "seed": pack.default_seed,
            "style_pack": pack.name,
        }
