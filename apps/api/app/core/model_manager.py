import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, Optional, Protocol

from app.core.model_registry import ModelRegistry, ModelSpec

logger = logging.getLogger(__name__)


class ModelProvider(Protocol):
    async def load(self, spec: ModelSpec) -> None: ...
    async def unload(self, spec: ModelSpec) -> None: ...
    async def is_loaded(self, spec: ModelSpec) -> bool: ...


class NoopProvider:
    """Safe provider used until a concrete runtime adapter is configured."""

    async def load(self, spec: ModelSpec) -> None:
        logger.info("Model load requested: %s (%s)", spec.name, spec.provider)

    async def unload(self, spec: ModelSpec) -> None:
        logger.info("Model unload requested: %s (%s)", spec.name, spec.provider)

    async def is_loaded(self, spec: ModelSpec) -> bool:
        return False


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
        self.providers = providers or {}
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

    def resident_models(self) -> list[str]:
        return list(self._resident.keys())

    def status(self) -> dict:
        return {
            "capacity_gb": self.vram.capacity_gb,
            "safety_margin_gb": self.vram.safety_margin_gb,
            "reserved_gb": self.vram.reserved_gb,
            "available_gb": self.vram.available_gb,
            "resident_models": self.resident_models(),
        }
