"""Load the configurable genre registry used by Movie Studio."""
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


REGISTRY_PATH = Path(__file__).resolve().parents[4] / "config" / "movie_genres" / "registry.yaml"


@lru_cache(maxsize=1)
def get_genre_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        raise RuntimeError(f"Movie genre registry not found: {REGISTRY_PATH}")
    with REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    profiles = data.get("profiles", [])
    ids = [item.get("id") for item in profiles]
    if not profiles or len(ids) != len(set(ids)) or any(not item for item in ids):
        raise ValueError("Movie genre registry must contain unique, non-empty profile IDs")
    return data


def validate_genres(genre_ids: list[str]) -> list[str]:
    registry = get_genre_registry()
    known = {item["id"] for item in registry.get("profiles", [])}
    allow_custom = bool(registry.get("allow_custom_genres", False))
    unknown = [genre for genre in genre_ids if genre not in known]
    if unknown and not allow_custom:
        raise ValueError(f"Unsupported genre profile(s): {', '.join(unknown)}")
    if not genre_ids:
        return [registry.get("default_profile", "neutral")]
    return genre_ids
