import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional

from app.core.model_registry import ModelRegistry, ModelSpec
from app.core.model_providers import (
    ModelProvider,
    NoopProvider,
    OllamaModelProvider,
    ComfyUIModelProvider,
    TorchModelProvider,
    MockTrackingProvider,
)

logger = logging.getLogger(__name__)


@dataclass
class Residency:
    model: str
    loaded_at: float
    last_used_at: float


class VRAMManager:
    def __init__(self, capacity_gb: float = 32.0, safety_margin_gb: float = 2.0):
        self.capacity_gb = capacity_gb
        self.safety_margin_gb = safety_margin_gb
        self._reserved_gb = 0.0

    @property
    def available_gb(self) -> float:
        return max(0.0, self.capacity_gb - self.safety_margin_gb - self._reserved_gb)

    def can_reserve(self, amount_gb: float) -> bool:
        return amount_gb <= self.available_gb

    def reserve(self, amount_gb: float) -> None:
        if not self.can_reserve(amount_gb):
            raise RuntimeError(
                f"Insufficient planned VRAM: need {amount_gb:.1f} GB, "
                f"available {self.available_gb:.1f} GB"
            )
        self._reserved_gb += amount_gb

    def release(self, amount_gb: float) -> None:
        self._reserved_gb = max(0.0, self._reserved_gb - amount_gb)

    @property
    def reserved_gb(self) -> float:
        return self._reserved_gb


def _default_providers() -> Dict[str, ModelProvider]:
    return {
        "ollama": OllamaModelProvider(),
        "comfyui": ComfyUIModelProvider(),
        "torch": TorchModelProvider(),
        "kokoro": TorchModelProvider(),
        "mock": NoopProvider(),
    }


class ModelManager:
    """Coordinates model residency on a single GPU.

    The manager deliberately does not assume that every backend has the same
    unload API. Provider adapters implement the actual lifecycle. At most the
    configured VRAM budget is reserved, and a model switch evicts other local
    models before loading the requested one.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        vram: Optional[VRAMManager] = None,
        providers: Optional[Dict[str, ModelProvider]] = None,
    ):
        self.registry = registry or ModelRegistry.for_5090()
        self.vram = vram or VRAMManager()
        self.providers = providers if providers is not None else _default_providers()
        self._resident: Dict[str, Residency] = {}
        self._lock = asyncio.Lock()

    def provider_for(self, spec: ModelSpec) -> ModelProvider:
        return self.providers.get(spec.provider, NoopProvider())

    async def ensure_loaded(self, model: str) -> ModelSpec:
        spec = self.registry.get(model)
        async with self._lock:
            now = time.monotonic()
            if model in self._resident:
                self._resident[model].last_used_at = now
                return spec

            if not self.vram.can_reserve(spec.vram_gb):
                await self._evict_until_fit(spec.vram_gb)
            self.vram.reserve(spec.vram_gb)
            try:
                await self.provider_for(spec).load(spec)
            except Exception:
                self.vram.release(spec.vram_gb)
                raise
            self._resident[model] = Residency(model, now, now)
            logger.info("Model resident: %s (%.1f GB planned)", model, spec.vram_gb)
            return spec

    async def release(self, model: str) -> None:
        async with self._lock:
            await self._release_unlocked(model)

    async def _release_unlocked(self, model: str) -> None:
        residency = self._resident.pop(model, None)
        if not residency:
            return
        spec = self.registry.get(model)
        try:
            await self.provider_for(spec).unload(spec)
        finally:
            self.vram.release(spec.vram_gb)
        logger.info("Model evicted: %s", model)

    async def _evict_until_fit(self, required_gb: float) -> None:
        while not self.vram.can_reserve(required_gb):
            if not self._resident:
                raise RuntimeError(
                    f"No resident model can be evicted to fit {required_gb:.1f} GB"
                )
            oldest = min(self._resident.values(), key=lambda r: r.last_used_at)
            await self._release_unlocked(oldest.model)

    async def release_idle(self, idle_seconds: int = 0) -> list[str]:
        now = time.monotonic()
        async with self._lock:
            candidates = [
                r.model for r in self._resident.values()
                if idle_seconds <= 0 or now - r.last_used_at >= idle_seconds
            ]
            for model in candidates:
                await self._release_unlocked(model)
            return candidates

    @asynccontextmanager
    async def session(self, model: str) -> AsyncIterator[ModelSpec]:
        """
        Context manager ensuring the model is resident in VRAM during execution,
        and automatically released when exiting if configured with unload_after_use=True.
        """
        spec = await self.ensure_loaded(model)
        try:
            yield spec
        finally:
            if spec.unload_after_use:
                await self.release(model)

    def resident_models(self) -> list[str]:
        return list(self._resident.keys())

    def status(self) -> dict:
        return {
            "capacity_gb": self.vram.capacity_gb,
            "safety_margin_gb": self.vram.safety_margin_gb,
            "reserved_gb": self.vram.reserved_gb,
            "available_gb": self.vram.available_gb,
            "resident_models": self.resident_models(),
            "hardware_cuda": self.get_hardware_cuda_vram(),
        }

    @staticmethod
    def get_hardware_cuda_vram() -> Optional[dict]:
        try:
            import torch
            if torch.cuda.is_available():
                free_bytes, total_bytes = torch.cuda.mem_get_info()
                return {
                    "free_gb": round(free_bytes / (1024**3), 2),
                    "total_gb": round(total_bytes / (1024**3), 2),
                    "allocated_gb": round(torch.cuda.memory_allocated() / (1024**3), 2),
                }
        except Exception:
            pass
        return None

    @classmethod
    def for_profile(
        cls,
        profile: str = "5090",
        providers: Optional[Dict[str, ModelProvider]] = None
    ) -> "ModelManager":
        """Factory creating a ModelManager configured for the designated compute profile."""
        if profile.lower() in ("mac", "apple", "cpu"):
            return cls(
                registry=ModelRegistry.for_mac(),
                vram=VRAMManager(capacity_gb=12.0, safety_margin_gb=1.0),
                providers=providers,
            )
        return cls(
            registry=ModelRegistry.for_5090(),
            vram=VRAMManager(capacity_gb=32.0, safety_margin_gb=2.0),
            providers=providers,
        )
