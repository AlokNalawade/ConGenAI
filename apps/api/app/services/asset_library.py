import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

LIBRARY_CATEGORIES = [
    "characters",
    "backgrounds",
    "music",
    "sound_effects",
    "voices",
    "fonts",
    "templates",
    "styles"
]

class AssetLibraryManager:
    def __init__(self, base_dir: str = "data/library"):
        self.base_dir = os.path.abspath(base_dir)
        self.ensure_library_structure()

    def ensure_library_structure(self):
        for category in LIBRARY_CATEGORIES:
            cat_dir = os.path.join(self.base_dir, category)
            os.makedirs(cat_dir, exist_ok=True)
        logger.info(f"Initialized Local Asset Library structure at {self.base_dir}")

    def list_category_assets(self, category: str) -> List[str]:
        cat_dir = os.path.join(self.base_dir, category)
        if not os.path.exists(cat_dir):
            return []
        return [os.path.join(cat_dir, f) for f in os.listdir(cat_dir) if not f.startswith(".")]

asset_library = AssetLibraryManager()
