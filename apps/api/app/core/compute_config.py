import os
from pydantic import BaseModel
from typing import Dict, Any

class ProviderConfig(BaseModel):
    provider: str
    model: str
    device: str = "cpu"

class ComputeConfig(BaseModel):
    dev_mode: bool = True
    profile: str = "mac"
    llm: ProviderConfig = ProviderConfig(provider="ollama", model="llama3:latest", device="cpu")
    image: ProviderConfig = ProviderConfig(provider="mock", model="placeholder", device="cpu")
    tts: ProviderConfig = ProviderConfig(provider="mock", model="silent", device="cpu")
    video: ProviderConfig = ProviderConfig(provider="ffmpeg", model="default", device="cpu")

def load_compute_config() -> ComputeConfig:
    profile = os.getenv("PROFILE", "").lower()
    is_dev = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")

    if profile == "5090":
        return ComputeConfig(
            dev_mode=False,
            profile="5090",
            llm=ProviderConfig(provider=os.getenv("GPU_LLM_PROVIDER", "ollama"), model=os.getenv("GPU_LLM_MODEL", "qwen2.5:14b"), device="cuda"),
            image=ProviderConfig(provider=os.getenv("GPU_IMAGE_PROVIDER", "comfyui"), model=os.getenv("GPU_IMAGE_MODEL", "flux"), device="cuda"),
            tts=ProviderConfig(provider=os.getenv("GPU_TTS_PROVIDER", "kokoro"), model=os.getenv("GPU_TTS_MODEL", "kokoro-v1.0"), device="cuda"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    elif profile == "cloud":
        return ComputeConfig(
            dev_mode=False,
            profile="cloud",
            llm=ProviderConfig(provider="openai", model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), device="cloud"),
            image=ProviderConfig(provider="openai", model="dall-e-3", device="cloud"),
            tts=ProviderConfig(provider="openai", model="tts-1", device="cloud"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    elif profile == "hybrid":
        return ComputeConfig(
            dev_mode=False,
            profile="hybrid",
            llm=ProviderConfig(provider="openai", model="gpt-4o-mini", device="cloud"),
            image=ProviderConfig(provider="comfyui", model="flux", device="cuda"),
            tts=ProviderConfig(provider="kokoro", model="kokoro-v1.0", device="cuda"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    else: # mac / default dev
        return ComputeConfig(
            dev_mode=True,
            profile="mac",
            llm=ProviderConfig(provider="ollama", model=os.getenv("DEFAULT_MODEL", "llama3:latest"), device="cpu"),
            image=ProviderConfig(provider="mock", model="placeholder", device="cpu"),
            tts=ProviderConfig(provider="mock", model="silent", device="cpu"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )

compute_config = load_compute_config()
