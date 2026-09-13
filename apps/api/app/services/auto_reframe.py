"""Saliency Focal-Point Auto-Reframe Service (Opus Clip style).

Intelligently reframes horizontal (16:9) or arbitrary visual assets into vertical (9:16) Shorts:
- Computes visual center-of-interest (luminance/edge saliency center-of-mass) using Pillow
- Dynamically centers the vertical crop window on the primary subject instead of blind center-cropping
- Prevents decapitating faces or cutting off diagrams
"""

from typing import Tuple, Optional
from PIL import Image, ImageFilter
from pydantic import BaseModel


class CropCoordinates(BaseModel):
    left: int
    top: int
    right: int
    bottom: int
    focal_x: int
    focal_y: int
    target_width: int
    target_height: int


class AutoReframeService:
    @staticmethod
    def find_focal_point(image: Image.Image) -> Tuple[int, int]:
        """Compute visual saliency focal point using edge gradient and contrast center-of-mass."""
        thumb_w = 120
        thumb_h = max(1, int(120 * image.height / max(1, image.width)))
        thumb = image.convert("L").resize((thumb_w, thumb_h), Image.Resampling.BILINEAR)
        edges = thumb.filter(ImageFilter.FIND_EDGES)
        
        pixels_edge = edges.load()
        pixels_lum = thumb.load()
        
        total_lum = sum(pixels_lum[x, y] for y in range(thumb_h) for x in range(thumb_w))
        mean_lum = total_lum / (thumb_w * thumb_h)
        
        total_weight = 0
        sum_x = 0
        sum_y = 0
        
        for y in range(thumb_h):
            for x in range(thumb_w):
                edge_val = pixels_edge[x, y]
                contrast_val = abs(pixels_lum[x, y] - mean_lum)
                weight = edge_val + contrast_val
                if weight > 10:
                    total_weight += weight
                    sum_x += x * weight
                    sum_y += y * weight
        
        if total_weight == 0:
            return (image.width // 2, image.height // 2)
        
        norm_x = sum_x / total_weight / thumb_w
        norm_y = sum_y / total_weight / thumb_h
        
        focal_x = int(norm_x * image.width)
        focal_y = int(norm_y * image.height)
        return (focal_x, focal_y)

    @classmethod
    def calculate_vertical_crop(
        cls,
        image_path_or_img,
        target_aspect_ratio: float = 9.0 / 16.0,  # 0.5625 for 9:16 vertical
    ) -> CropCoordinates:
        """Calculate optimal crop window centered on visual focal point."""
        if isinstance(image_path_or_img, str):
            img = Image.open(image_path_or_img)
        else:
            img = image_path_or_img

        w, h = img.size
        focal_x, focal_y = cls.find_focal_point(img)

        current_ratio = w / h

        if current_ratio > target_aspect_ratio:
            # Image is wider than target: crop width
            target_w = int(h * target_aspect_ratio)
            target_h = h

            # Center crop around focal_x, bounded within [0, w]
            left = max(0, min(focal_x - (target_w // 2), w - target_w))
            top = 0
            right = left + target_w
            bottom = h
        else:
            # Image is taller than target: crop height
            target_w = w
            target_h = int(w / target_aspect_ratio)

            # Center crop around focal_y, bounded within [0, h]
            left = 0
            top = max(0, min(focal_y - (target_h // 2), h - target_h))
            right = w
            bottom = top + target_h

        return CropCoordinates(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            focal_x=focal_x,
            focal_y=focal_y,
            target_width=target_w,
            target_height=target_h,
        )

    @classmethod
    def reframe_image(
        cls,
        input_image_path: str,
        output_image_path: str,
        target_resolution: Tuple[int, int] = (1080, 1920),
    ) -> str:
        """Crop and resize image to exact target vertical resolution centered on focal point."""
        img = Image.open(input_image_path)
        crop = cls.calculate_vertical_crop(img, target_aspect_ratio=target_resolution[0] / target_resolution[1])
        cropped = img.crop((crop.left, crop.top, crop.right, crop.bottom))
        resized = cropped.resize(target_resolution, Image.Resampling.LANCZOS)
        resized.save(output_image_path)
        return output_image_path
