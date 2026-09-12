from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    stage: str
    vram_gb: float
    keep_alive_seconds: int = 0
    unload_after_use: bool = True


class ModelRegistry:
    """Declarative registry of models ConGenAI may load onto the local GPU.

    VRAM values are conservative planning estimates, not measurements. The
    registry is intentionally provider-neutral so Ollama, ComfyUI and future
    video/audio engines can share the same scheduler contract.
    """

    def __init__(self, specs: Optional[Dict[str, ModelSpec]] = None):
        self._specs = specs or {}

    def register(self, spec: ModelSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ModelSpec:
        if name not in self._specs:
            raise KeyError(f"Model '{name}' is not registered")
        return self._specs[name]

    def all(self) -> Dict[str, ModelSpec]:
        return dict(self._specs)

    @classmethod
    def for_5090(cls) -> "ModelRegistry":
        return cls({
            "qwen2.5:14b": ModelSpec("qwen2.5:14b", "ollama", "text", 10.0),
            "qwen3:35b": ModelSpec("qwen3:35b", "ollama", "text", 24.0),
            "deepseek-r1": ModelSpec("deepseek-r1", "ollama", "text", 24.0),
            "flux": ModelSpec("flux", "comfyui", "image", 18.0),
            "ltx-2.3": ModelSpec("ltx-2.3", "comfyui", "video", 24.0),
            "wan-2.2": ModelSpec("wan-2.2", "comfyui", "video", 28.0),
            "kokoro-v1.0": ModelSpec("kokoro-v1.0", "kokoro", "audio", 4.0),
        })
