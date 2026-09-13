import asyncio
import gc
import logging
import os
from typing import Dict, List, Optional, Protocol, Set
import httpx

from app.core.model_registry import ModelSpec

logger = logging.getLogger(__name__)


class ModelProvider(Protocol):
    """Protocol for model runtime lifecycle adapters."""
    async def load(self, spec: ModelSpec) -> None: ...
    async def unload(self, spec: ModelSpec) -> None: ...
    async def is_loaded(self, spec: ModelSpec) -> bool: ...


class NoopProvider:
    """Fallback provider when no active runtime adapter is configured."""

    async def load(self, spec: ModelSpec) -> None:
        logger.info("Model load requested (noop): %s (%s)", spec.name, spec.provider)

    async def unload(self, spec: ModelSpec) -> None:
        logger.info("Model unload requested (noop): %s (%s)", spec.name, spec.provider)

    async def is_loaded(self, spec: ModelSpec) -> bool:
        return False


class MockTrackingProvider:
    """
    In-memory tracking provider used for tests and offline development.
    Records load and unload calls and tracks simulated resident models.
    """

    def __init__(self):
        self.loaded_models: Set[str] = set()
        self.load_history: List[str] = []
        self.unload_history: List[str] = []

    async def load(self, spec: ModelSpec) -> None:
        self.loaded_models.add(spec.name)
        self.load_history.append(spec.name)
        logger.info("[MockTrackingProvider] Loaded %s (total loaded: %d)", spec.name, len(self.loaded_models))

    async def unload(self, spec: ModelSpec) -> None:
        self.loaded_models.discard(spec.name)
        self.unload_history.append(spec.name)
        logger.info("[MockTrackingProvider] Unloaded %s (remaining loaded: %d)", spec.name, len(self.loaded_models))

    async def is_loaded(self, spec: ModelSpec) -> bool:
        return spec.name in self.loaded_models


class OllamaModelProvider:
    """
    Controls model residency in Ollama via its HTTP API.

    - Load: POST /api/generate with keep_alive='10m' (preloads weights into VRAM).
    - Unload: POST /api/generate with keep_alive=0 (instantly frees VRAM allocations).
    - is_loaded: GET /api/ps to verify residency in GPU memory.
    """

    def __init__(self, host: Optional[str] = None, client: Optional[httpx.AsyncClient] = None):
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=30.0)

    async def load(self, spec: ModelSpec) -> None:
        keep_alive = f"{spec.keep_alive_seconds}s" if spec.keep_alive_seconds > 0 else "10m"
        client = await self._get_client()
        try:
            logger.info("Preloading Ollama model %s (keep_alive=%s)", spec.name, keep_alive)
            resp = await client.post(
                f"{self.host}/api/generate",
                json={"model": spec.name, "keep_alive": keep_alive},
            )
            resp.raise_for_status()
            logger.info("Ollama model %s loaded successfully into memory", spec.name)
        except Exception as e:
            logger.error("Failed to preload Ollama model %s: %s", spec.name, e)
            raise
        finally:
            if self._client is None:
                await client.aclose()

    async def unload(self, spec: ModelSpec) -> None:
        client = await self._get_client()
        try:
            logger.info("Unloading Ollama model %s (keep_alive=0)", spec.name)
            resp = await client.post(
                f"{self.host}/api/generate",
                json={"model": spec.name, "keep_alive": 0},
            )
            resp.raise_for_status()
            logger.info("Ollama model %s evicted from VRAM", spec.name)
        except Exception as e:
            logger.warning("Error unloading Ollama model %s: %s", spec.name, e)
        finally:
            if self._client is None:
                await client.aclose()

    async def is_loaded(self, spec: ModelSpec) -> bool:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.host}/api/ps")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name") for m in data.get("models", [])]
                return spec.name in models or any(m.startswith(spec.name) for m in models if m)
            return False
        except Exception:
            return False
        finally:
            if self._client is None:
                await client.aclose()


class ComfyUIModelProvider:
    """
    Controls VRAM residency for ComfyUI (Flux, LTX-Video, Wan).

    ComfyUI automatically loads models on workflow execution, but VRAM remains
    allocated until freed.
    - Unload: POST /free with {"unload_models": True, "free_memory": True}
      purges model weights from GPU memory and empties the PyTorch CUDA cache.
    """

    def __init__(self, host: Optional[str] = None, client: Optional[httpx.AsyncClient] = None):
        self.host = (host or os.getenv("COMFYUI_HOST", "http://127.0.0.1:8188")).rstrip("/")
        self._client = client

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(timeout=30.0)

    async def load(self, spec: ModelSpec) -> None:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.host}/system_stats")
            resp.raise_for_status()
            logger.info("ComfyUI server at %s verified ready for model %s", self.host, spec.name)
        except Exception as e:
            logger.warning("ComfyUI server at %s not responding during load check: %s", self.host, e)
        finally:
            if self._client is None:
                await client.aclose()

    async def unload(self, spec: ModelSpec) -> None:
        client = await self._get_client()
        try:
            logger.info("Freeing ComfyUI VRAM (unload_models=True, free_memory=True)")
            resp = await client.post(
                f"{self.host}/free",
                json={"unload_models": True, "free_memory": True},
            )
            resp.raise_for_status()
            logger.info("ComfyUI GPU VRAM cache successfully purged for %s", spec.name)
        except Exception as e:
            logger.warning("Failed to call ComfyUI /free endpoint for %s: %s", spec.name, e)
        finally:
            if self._client is None:
                await client.aclose()

    async def is_loaded(self, spec: ModelSpec) -> bool:
        client = await self._get_client()
        try:
            resp = await client.get(f"{self.host}/system_stats")
            return resp.status_code == 200
        except Exception:
            return False
        finally:
            if self._client is None:
                await client.aclose()


class TorchModelProvider:
    """
    Controls in-process PyTorch models (e.g. Kokoro TTS or diffusers).
    Forces Python garbage collection and clears CUDA memory cache.
    """

    async def load(self, spec: ModelSpec) -> None:
        logger.info("In-process Torch model %s ready", spec.name)

    async def unload(self, spec: ModelSpec) -> None:
        logger.info("Freeing in-process PyTorch VRAM for %s", spec.name)
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
                logger.info("PyTorch CUDA cache emptied successfully")
        except ImportError:
            pass

    async def is_loaded(self, spec: ModelSpec) -> bool:
        return False
