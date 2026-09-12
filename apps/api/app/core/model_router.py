import os
from typing import Dict

from app.core.model_registry import ModelRegistry


class ModelRouter:
    """Selects the model for each pipeline stage without hard-coding providers."""

    DEFAULTS = {
        "research": "qwen3:35b",
        "strategy": "qwen3:35b",
        "script": "qwen3:35b",
        "scene": "qwen3:35b",
        "image": "flux",
        "video": "ltx-2.3",
        "voice": "kokoro-v1.0",
    }

    def __init__(self, registry: ModelRegistry | None = None):
        self.registry = registry or ModelRegistry.for_5090()

    def route(self, stage: str, overrides: Dict[str, str] | None = None) -> str:
        overrides = overrides or {}
        model = overrides.get(stage) or os.getenv(f"MODEL_{stage.upper()}") or self.DEFAULTS.get(stage)
        if not model:
            raise ValueError(f"No model configured for pipeline stage '{stage}'")
        self.registry.get(model)  # fail fast on typos/unregistered models
        return model

    def route_pipeline(self, overrides: Dict[str, str] | None = None) -> Dict[str, str]:
        return {stage: self.route(stage, overrides) for stage in self.DEFAULTS}
