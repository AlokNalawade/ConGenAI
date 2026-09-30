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
            "qwen2.5:14b": ModelSpec("qwen2.5:14b", "ollama", "text", 10.0, unload_after_use=False),
            "qwen3:35b": ModelSpec("qwen3:35b", "ollama", "text", 24.0, unload_after_use=False),
            "deepseek-r1": ModelSpec("deepseek-r1", "ollama", "text", 24.0, unload_after_use=False),
            "flux": ModelSpec("flux", "comfyui", "image", 18.0, unload_after_use=False),
            "ltx-2.3": ModelSpec("ltx-2.3", "comfyui", "video", 24.0, unload_after_use=True),
            "wan-2.2": ModelSpec("wan-2.2", "comfyui", "video", 28.0, unload_after_use=True),
            "kokoro-v1.0": ModelSpec("kokoro-v1.0", "kokoro", "audio", 4.0, unload_after_use=True),
        })

    @classmethod
    def for_mac(cls) -> "ModelRegistry":
        return cls({
            "llama3:latest": ModelSpec("llama3:latest", "ollama", "text", 4.5),
            "llama3": ModelSpec("llama3", "ollama", "text", 4.5),
            "deepseek-r1:8b": ModelSpec("deepseek-r1:8b", "ollama", "text", 5.0),
            "deepseek-r1": ModelSpec("deepseek-r1", "ollama", "text", 5.0),
            "llama3.2:1b": ModelSpec("llama3.2:1b", "ollama", "text", 1.5),
            "llama3.2:3b": ModelSpec("llama3.2:3b", "ollama", "text", 2.5),
            "qwen2.5:1.5b": ModelSpec("qwen2.5:1.5b", "ollama", "text", 1.5),
            "qwen2.5:7b": ModelSpec("qwen2.5:7b", "ollama", "text", 4.5),
            "mock-image": ModelSpec("mock-image", "mock", "image", 0.0),
            "mock-video": ModelSpec("mock-video", "mock", "video", 0.0),
            "mock-audio": ModelSpec("mock-audio", "mock", "audio", 0.0),
            # H3 is executed by an external Apple-Silicon runner (MLX/Metal).
            # Memory is managed by that runner rather than ConGenAI's CUDA budget.
            "minimax-h3": ModelSpec("minimax-h3", "h3", "video", 0.0, unload_after_use=True),
        })

    @classmethod
    def for_profile(cls, profile: str = "5090") -> "ModelRegistry":
        if profile.lower() in ("mac", "apple", "cpu"):
            return cls.for_mac()
        return cls.for_5090()
