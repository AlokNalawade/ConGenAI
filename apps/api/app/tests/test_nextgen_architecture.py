import pytest
import uuid
import os
from app.workflows.workflow_state import WorkflowState, can_transition
from app.workflows.worker import job_manager
from app.core.compute_config import compute_config
from app.services.providers import OllamaProvider, MockImageProvider, MockTTSProvider
from app.services.subtitle_service import SubtitleService
from app.services.asset_library import asset_library
from app.services.templates import get_template

@pytest.mark.asyncio
async def test_workflow_state_resiliency():
    assert can_transition("idea", "researching") is True
    assert can_transition("researching", "strategizing") is True
    assert can_transition("researching", "scripting") is True
    assert can_transition("failed", "researching") is True
    assert can_transition("published", "analyzing_performance") is True

@pytest.mark.asyncio
async def test_job_worker_manager():
    from app.db.database import engine, AsyncSessionLocal
    from app.db.models import Content as DBContent
    await engine.dispose()

    async with AsyncSessionLocal() as db:
        content = DBContent(title="Job Test Content", status="idea")
        db.add(content)
        await db.commit()
        await db.refresh(content)
        content_id = str(content.id)

    job = await job_manager.create_job(content_id)
    assert job.job_id.startswith("job_")
    assert job.content_id == content_id
    assert job.status == "queued"
    
    fetched = await job_manager.get_job(job.job_id)
    assert fetched is not None
    assert fetched.content_id == content_id

@pytest.mark.asyncio
async def test_compute_config_dev_mode():
    assert compute_config.dev_mode is True
    assert compute_config.llm.provider == "ollama"
    assert compute_config.image.provider == "mock"

@pytest.mark.asyncio
async def test_ai_provider_abstractions():
    img_provider = MockImageProvider()
    path = await img_provider.generate_image("Test scene visual prompt", output_path="data/assets/images/test_mock.png")
    assert os.path.exists(path)

    tts_provider = MockTTSProvider()
    audio_path = await tts_provider.generate_audio("Hello ConGen AI test", output_path="data/assets/audio/test_mock.mp3")
    assert os.path.exists(audio_path)

@pytest.mark.asyncio
async def test_subtitle_generator():
    ass_path = "data/assets/subtitles/test.ass"
    res = SubtitleService.generate_ass_subtitle(
        text="This is an autonomous content generation test",
        duration=4.0,
        output_path=ass_path
    )
    assert os.path.exists(res)
    with open(res, "r") as f:
        content = f.read()
        assert "ConGen Animated Subtitles" in content

@pytest.mark.asyncio
async def test_asset_library_and_templates():
    assert len(asset_library.base_dir) > 0
    tmpl = get_template("Educational")
    assert tmpl.name == "Educational Explainer"
    assert "Hook Question" in tmpl.structure
