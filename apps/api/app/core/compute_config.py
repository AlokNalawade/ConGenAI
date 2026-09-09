import os
from pydantic import BaseModel
from typing import Dict, Any

class ProviderConfig(BaseModel):
    provider: str
    model: str
    device: str = "cpu"

class ComputeConfig(BaseModel):
    dev_mode: bool = True
    llm: ProviderConfig = ProviderConfig(provider="ollama", model="llama3:latest", device="cpu")
    image: ProviderConfig = ProviderConfig(provider="mock", model="placeholder", device="cpu")
    tts: ProviderConfig = ProviderConfig(provider="mock", model="silent", device="cpu")
    video: ProviderConfig = ProviderConfig(provider="ffmpeg", model="default", device="cpu")

def load_compute_config() -> ComputeConfig:
    is_dev = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")
    
    if is_dev:
        return ComputeConfig(
            dev_mode=True,
            llm=ProviderConfig(provider="ollama", model=os.getenv("DEFAULT_MODEL", "llama3:latest"), device="cpu"),
            image=ProviderConfig(provider="mock", model="placeholder", device="cpu"),
            tts=ProviderConfig(provider="mock", model="silent", device="cpu"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    else:
        # RTX 5090 Production GPU Configuration
        return ComputeConfig(
            dev_mode=False,
            llm=ProviderConfig(provider=os.getenv("GPU_LLM_PROVIDER", "ollama"), model=os.getenv("GPU_LLM_MODEL", "qwen2.5:14b"), device="cuda"),
            image=ProviderConfig(provider=os.getenv("GPU_IMAGE_PROVIDER", "comfyui"), model=os.getenv("GPU_IMAGE_MODEL", "flux"), device="cuda"),
            tts=ProviderConfig(provider=os.getenv("GPU_TTS_PROVIDER", "kokoro"), model=os.getenv("GPU_TTS_MODEL", "kokoro-v1.0"), device="cuda"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )

compute_config = load_compute_config()
