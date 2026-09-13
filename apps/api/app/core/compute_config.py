import os
import asyncio
from dataclasses import dataclass, field
from pydantic import BaseModel
from typing import Dict, Optional

class ProviderConfig(BaseModel):
    provider: str
    model: str
    device: str = "cpu"


@dataclass
class ResourceSemaphores:
    """
    Global asyncio.Semaphore instances for GPU/CPU resource scheduling.
    Created once at worker startup and passed into ContentPipeline.

    These enforce concurrency limits *across all concurrent pipeline jobs*,
    preventing resource contention (e.g. 3 jobs all running ComfyUI at once).
    """
    llm: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(4))
    image_gpu: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    tts: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))
    ffmpeg: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))
    research: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(4))
    qa: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(2))


class ComputeConfig(BaseModel):
    dev_mode: bool = True
    profile: str = "mac"
    allow_ephemeral_jobs: bool = False
    image_concurrency: int = 2
    tts_concurrency: int = 2
    max_concurrent_jobs: int = 1
    worker_heartbeat_seconds: int = 30
    stale_job_timeout_seconds: int = 300
    # Per-resource concurrency caps (used by ResourceSemaphores factory)
    llm_concurrency: int = 4
    image_gpu_concurrency: int = 1
    tts_concurrency_cap: int = 2
    ffmpeg_concurrency: int = 2
    research_concurrency: int = 4
    qa_concurrency: int = 2
    llm: ProviderConfig = ProviderConfig(provider="ollama", model="llama3:latest", device="cpu")
    image: ProviderConfig = ProviderConfig(provider="mock", model="placeholder", device="cpu")
    tts: ProviderConfig = ProviderConfig(provider="mock", model="silent", device="cpu")
    video: ProviderConfig = ProviderConfig(provider="ffmpeg", model="default", device="cpu")

    def create_semaphores(self) -> ResourceSemaphores:
        """
        Create a fresh set of resource semaphores sized for this compute profile.
        Call once at arq worker startup; pass the returned object into ContentPipeline.
        """
        return ResourceSemaphores(
            llm=asyncio.Semaphore(self.llm_concurrency),
            image_gpu=asyncio.Semaphore(self.image_gpu_concurrency),
            tts=asyncio.Semaphore(self.tts_concurrency_cap),
            ffmpeg=asyncio.Semaphore(self.ffmpeg_concurrency),
            research=asyncio.Semaphore(self.research_concurrency),
            qa=asyncio.Semaphore(self.qa_concurrency),
        )

    class Config:
        arbitrary_types_allowed = True


def load_compute_config() -> ComputeConfig:
    profile = os.getenv("PROFILE", "").lower()
    is_dev = os.getenv("DEV_MODE", "true").lower() in ("true", "1", "yes")
    allow_ephemeral = os.getenv("ALLOW_EPHEMERAL_JOBS", "false").lower() in ("true", "1", "yes")
    img_conc = int(os.getenv("IMAGE_CONCURRENCY", "2"))
    tts_conc = int(os.getenv("TTS_CONCURRENCY", "2"))

    if profile == "5090":
        return ComputeConfig(
            dev_mode=False,
            profile="5090",
            allow_ephemeral_jobs=allow_ephemeral,
            image_concurrency=img_conc,
            tts_concurrency=tts_conc,
            max_concurrent_jobs=int(os.getenv("MAX_CONCURRENT_JOBS", "3")),
            worker_heartbeat_seconds=int(os.getenv("WORKER_HEARTBEAT_SECONDS", "30")),
            stale_job_timeout_seconds=int(os.getenv("STALE_JOB_TIMEOUT_SECONDS", "300")),
            # RTX 5090 resource caps
            llm_concurrency=4,
            image_gpu_concurrency=1,  # ComfyUI/Flux is single-GPU
            tts_concurrency_cap=2,
            ffmpeg_concurrency=2,
            research_concurrency=4,
            llm=ProviderConfig(provider=os.getenv("GPU_LLM_PROVIDER", "ollama"), model=os.getenv("GPU_LLM_MODEL", "qwen2.5:14b"), device="cuda"),
            image=ProviderConfig(provider=os.getenv("GPU_IMAGE_PROVIDER", "comfyui"), model=os.getenv("GPU_IMAGE_MODEL", "flux"), device="cuda"),
            tts=ProviderConfig(provider=os.getenv("GPU_TTS_PROVIDER", "kokoro"), model=os.getenv("GPU_TTS_MODEL", "kokoro-v1.0"), device="cuda"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    elif profile == "cloud":
        return ComputeConfig(
            dev_mode=False,
            profile="cloud",
            allow_ephemeral_jobs=allow_ephemeral,
            image_concurrency=img_conc,
            tts_concurrency=tts_conc,
            llm_concurrency=8,
            image_gpu_concurrency=4,  # cloud API parallelism
            tts_concurrency_cap=4,
            ffmpeg_concurrency=4,
            research_concurrency=8,
            llm=ProviderConfig(provider="openai", model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), device="cloud"),
            image=ProviderConfig(provider="openai", model="dall-e-3", device="cloud"),
            tts=ProviderConfig(provider="openai", model="tts-1", device="cloud"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    elif profile == "hybrid":
        return ComputeConfig(
            dev_mode=False,
            profile="hybrid",
            allow_ephemeral_jobs=allow_ephemeral,
            image_concurrency=img_conc,
            tts_concurrency=tts_conc,
            llm_concurrency=4,
            image_gpu_concurrency=1,
            tts_concurrency_cap=2,
            ffmpeg_concurrency=2,
            research_concurrency=4,
            llm=ProviderConfig(provider="openai", model="gpt-4o-mini", device="cloud"),
            image=ProviderConfig(provider="comfyui", model="flux", device="cuda"),
            tts=ProviderConfig(provider="kokoro", model="kokoro-v1.0", device="cuda"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )
    else:  # mac / default dev
        return ComputeConfig(
            dev_mode=True,
            profile="mac",
            allow_ephemeral_jobs=allow_ephemeral,
            image_concurrency=img_conc,
            tts_concurrency=tts_conc,
            llm_concurrency=2,
            image_gpu_concurrency=1,
            tts_concurrency_cap=2,
            ffmpeg_concurrency=1,
            research_concurrency=2,
            llm=ProviderConfig(provider="ollama", model=os.getenv("DEFAULT_MODEL", "llama3:latest"), device="cpu"),
            image=ProviderConfig(provider="mock", model="placeholder", device="cpu"),
            tts=ProviderConfig(provider="mock", model="silent", device="cpu"),
            video=ProviderConfig(provider="ffmpeg", model="default", device="cpu")
        )

compute_config = load_compute_config()
