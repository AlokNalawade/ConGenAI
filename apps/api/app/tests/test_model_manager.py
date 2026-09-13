import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.core.model_registry import ModelRegistry, ModelSpec
from app.core.model_manager import ModelManager, VRAMManager
from app.core.model_providers import (
    MockTrackingProvider,
    OllamaModelProvider,
    ComfyUIModelProvider,
    TorchModelProvider,
)
from app.core.model_router import ModelRouter


@pytest.mark.asyncio
async def test_vram_manager_budget_and_reservation():
    # 32 GB capacity with 2 GB safety margin = 30 GB usable
    vram = VRAMManager(capacity_gb=32.0, safety_margin_gb=2.0)
    assert vram.available_gb == 30.0
    assert vram.reserved_gb == 0.0

    # Reserve 24 GB for Qwen3
    assert vram.can_reserve(24.0) is True
    vram.reserve(24.0)
    assert vram.reserved_gb == 24.0
    assert vram.available_gb == 6.0

    # Attempt to reserve 18 GB for Flux without evicting -> must fail
    assert vram.can_reserve(18.0) is False
    with pytest.raises(RuntimeError, match="Insufficient planned VRAM"):
        vram.reserve(18.0)

    # Release 24 GB -> now can fit 18 GB
    vram.release(24.0)
    assert vram.reserved_gb == 0.0
    assert vram.available_gb == 30.0
    vram.reserve(18.0)
    assert vram.reserved_gb == 18.0
    assert vram.available_gb == 12.0


@pytest.mark.asyncio
async def test_dynamic_model_loading_and_manual_release():
    tracker = MockTrackingProvider()
    registry = ModelRegistry({
        "qwen2.5:14b": ModelSpec("qwen2.5:14b", "ollama", "text", 10.0),
        "flux": ModelSpec("flux", "comfyui", "image", 18.0),
    })
    manager = ModelManager(
        registry=registry,
        vram=VRAMManager(capacity_gb=32.0, safety_margin_gb=2.0),
        providers={"ollama": tracker, "comfyui": tracker},
    )

    # 1. Load Qwen
    spec = await manager.ensure_loaded("qwen2.5:14b")
    assert spec.name == "qwen2.5:14b"
    assert "qwen2.5:14b" in tracker.loaded_models
    assert "qwen2.5:14b" in manager.resident_models()
    assert manager.vram.reserved_gb == 10.0

    # 2. Release Qwen
    await manager.release("qwen2.5:14b")
    assert "qwen2.5:14b" not in tracker.loaded_models
    assert "qwen2.5:14b" not in manager.resident_models()
    assert manager.vram.reserved_gb == 0.0


@pytest.mark.asyncio
async def test_vram_overcommit_automatic_eviction_5090():
    """
    Simulates the exact 5090 pipeline scenario:
    - Step 1: Script agent loads Qwen3 (24 GB). Total reserved: 24/32 GB.
    - Step 2: Image agent requests Flux (18 GB).
      24 + 18 = 42 GB > 30 GB usable.
      Manager must automatically evict Qwen3 before loading Flux!
    """
    tracker = MockTrackingProvider()
    registry = ModelRegistry.for_5090()
    manager = ModelManager(
        registry=registry,
        vram=VRAMManager(capacity_gb=32.0, safety_margin_gb=2.0),
        providers={"ollama": tracker, "comfyui": tracker},
    )

    # Step 1: Load Qwen3 (24 GB)
    await manager.ensure_loaded("qwen3:35b")
    assert manager.resident_models() == ["qwen3:35b"]
    assert manager.vram.reserved_gb == 24.0
    assert tracker.loaded_models == {"qwen3:35b"}

    # Step 2: Request Flux (18 GB) -> Qwen3 must be evicted first!
    await manager.ensure_loaded("flux")
    assert "qwen3:35b" not in manager.resident_models()
    assert "flux" in manager.resident_models()
    assert manager.vram.reserved_gb == 18.0
    assert tracker.loaded_models == {"flux"}
    assert tracker.unload_history == ["qwen3:35b"]

    # Step 3: Request Video model LTX-2.3 (24 GB) -> Flux must be evicted!
    await manager.ensure_loaded("ltx-2.3")
    assert "flux" not in manager.resident_models()
    assert "ltx-2.3" in manager.resident_models()
    assert manager.vram.reserved_gb == 24.0
    assert tracker.loaded_models == {"ltx-2.3"}
    assert tracker.unload_history == ["qwen3:35b", "flux"]


@pytest.mark.asyncio
async def test_lru_eviction_order():
    """When multiple small models fit in VRAM, the least recently used is evicted first."""
    tracker = MockTrackingProvider()
    registry = ModelRegistry({
        "model_a": ModelSpec("model_a", "mock", "text", 8.0),
        "model_b": ModelSpec("model_b", "mock", "text", 8.0),
        "model_c": ModelSpec("model_c", "mock", "text", 20.0),
    })
    # Usable VRAM = 20 GB
    manager = ModelManager(
        registry=registry,
        vram=VRAMManager(capacity_gb=22.0, safety_margin_gb=2.0),
        providers={"mock": tracker},
    )

    await manager.ensure_loaded("model_a")  # loaded first
    await manager.ensure_loaded("model_b")  # loaded second (8 + 8 = 16 GB reserved)

    # Touch model_a to make it more recently used than model_b
    await manager.ensure_loaded("model_a")

    # Load model_c (20 GB). Needs 16 GB freed.
    # Because model_b was used least recently, model_b should be evicted first, then model_a.
    await manager.ensure_loaded("model_c")
    assert manager.resident_models() == ["model_c"]
    assert tracker.unload_history[0] == "model_b"
    assert tracker.unload_history[1] == "model_a"


@pytest.mark.asyncio
async def test_async_session_context_manager():
    """Context manager loads on enter and unloads on exit when unload_after_use=True."""
    tracker = MockTrackingProvider()
    registry = ModelRegistry({
        "flux": ModelSpec("flux", "comfyui", "image", 18.0, unload_after_use=True),
    })
    manager = ModelManager(
        registry=registry,
        vram=VRAMManager(capacity_gb=32.0, safety_margin_gb=2.0),
        providers={"comfyui": tracker},
    )

    assert "flux" not in tracker.loaded_models
    async with manager.session("flux") as spec:
        assert spec.name == "flux"
        assert "flux" in tracker.loaded_models
        assert manager.vram.reserved_gb == 18.0

    # Exited context -> automatically evicted
    assert "flux" not in tracker.loaded_models
    assert manager.vram.reserved_gb == 0.0


@pytest.mark.asyncio
async def test_ollama_provider_api_contracts():
    """Asserts that OllamaModelProvider calls the exact Ollama REST endpoints with correct payloads."""
    mock_post = AsyncMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.raise_for_status = lambda: None

    mock_resp_get = AsyncMock()
    mock_resp_get.status_code = 200
    mock_resp_get.json = lambda: {
        "models": [{"name": "qwen2.5:14b:latest", "size_vram": 10000000}]
    }
    mock_get = AsyncMock(return_value=mock_resp_get)

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = mock_post
    mock_client.get = mock_get

    provider = OllamaModelProvider(host="http://localhost:11434", client=mock_client)
    spec = ModelSpec("qwen2.5:14b", "ollama", "text", 10.0, keep_alive_seconds=300)

    # 1. Test Load
    await provider.load(spec)
    mock_post.assert_called_with(
        "http://localhost:11434/api/generate",
        json={"model": "qwen2.5:14b", "keep_alive": "300s"},
    )

    # 2. Test Unload (keep_alive: 0 immediately frees VRAM)
    await provider.unload(spec)
    mock_post.assert_called_with(
        "http://localhost:11434/api/generate",
        json={"model": "qwen2.5:14b", "keep_alive": 0},
    )

    # 3. Test is_loaded
    is_resident = await provider.is_loaded(spec)
    assert is_resident is True
    mock_get.assert_called_with("http://localhost:11434/api/ps")


@pytest.mark.asyncio
async def test_comfyui_provider_api_contracts():
    """Asserts that ComfyUIModelProvider calls /free with unload_models=True and free_memory=True."""
    mock_post = AsyncMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.raise_for_status = lambda: None

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = mock_post

    provider = ComfyUIModelProvider(host="http://127.0.0.1:8188", client=mock_client)
    spec = ModelSpec("flux", "comfyui", "image", 18.0)

    await provider.unload(spec)
    mock_post.assert_called_with(
        "http://127.0.0.1:8188/free",
        json={"unload_models": True, "free_memory": True},
    )


def test_model_router_stage_defaults_and_profiles():
    # 5090 Profile Defaults
    router_5090 = ModelRouter.for_profile("5090")
    assert router_5090.route("research") == "qwen3:35b"
    assert router_5090.route("image") == "flux"
    assert router_5090.route("video") == "ltx-2.3"

    # Mac Profile Defaults
    router_mac = ModelRouter.for_profile("mac")
    assert router_mac.route("research") in ("llama3:latest", "llama3.2:3b")
    assert router_mac.route("image") == "mock-image"

    # Explicit Override
    assert router_5090.route("script", overrides={"script": "deepseek-r1"}) == "deepseek-r1"


@pytest.mark.asyncio
async def test_content_pipeline_dynamic_model_lifecycle():
    """
    Verifies that ContentPipeline coordinates with ModelManager to load stage models
    and automatically evict conflicting models when VRAM limits would be exceeded.
    """
    from app.workflows.content_pipeline import ContentPipeline
    from app.workflows.workflow_context import WorkflowContext
    from app.models.ai_contracts import ResearchResult, StrategyResult, ScriptResult, ScenePlan, Scene

    tracker = MockTrackingProvider()
    manager = ModelManager(
        registry=ModelRegistry.for_5090(),
        vram=VRAMManager(capacity_gb=32.0, safety_margin_gb=2.0),
        providers={"ollama": tracker, "comfyui": tracker, "kokoro": tracker, "mock": tracker},
    )
    router = ModelRouter.for_profile("5090")

    pipeline = ContentPipeline(model_manager=manager, model_router=router)

    # 1. Simulate Research step
    research_model = pipeline.model_router.route("research")
    await pipeline.model_manager.ensure_loaded(research_model)
    assert "qwen3:35b" in manager.resident_models()
    assert manager.vram.reserved_gb == 24.0

    # 2. Simulate Strategy, Script, Scenes (all use qwen3:35b, stays resident with no eviction)
    script_model = pipeline.model_router.route("script")
    await pipeline.model_manager.ensure_loaded(script_model)
    assert len(tracker.unload_history) == 0  # no eviction needed, same model

    # 3. Simulate Media step (image model: flux 18 GB)
    # 24 GB + 18 GB = 42 GB > 30 GB usable -> must auto-evict qwen3:35b!
    image_model = pipeline.model_router.route("image")
    await pipeline.model_manager.ensure_loaded(image_model)
    assert "qwen3:35b" not in manager.resident_models()
    assert "flux" in manager.resident_models()
    assert manager.vram.reserved_gb == 18.0
    assert tracker.unload_history == ["qwen3:35b"]

    # 4. Simulate Video step (video model: ltx-2.3 24 GB)
    # 18 GB + 24 GB = 42 GB > 30 GB usable -> must auto-evict flux!
    video_model = pipeline.model_router.route("video")
    await pipeline.model_manager.ensure_loaded(video_model)
    assert "flux" not in manager.resident_models()
    assert "ltx-2.3" in manager.resident_models()
    assert manager.vram.reserved_gb == 24.0
    assert tracker.unload_history == ["qwen3:35b", "flux"]
