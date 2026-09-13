"""Unit and integration tests for Phase 1: Creatomate-style Templates & Content DNA Engine."""

import pytest
import os
import uuid
from app.templates.schema import (
    TrackType,
    AnimationType,
    ProgressIndicatorStyle,
    TemplateElement,
    CompositionScene,
    ContentComposition,
    TEMPLATE_PRESETS,
)
from app.templates.composition_engine import CompositionEngine
from app.services.video_service import VideoService
from app.models.content_dna import (
    ContentDNA,
    BrandArchetype,
    VoiceTone,
    VisualAesthetic,
    HookPhilosophy,
    DNAVariation,
    BatchDNAPlan,
)
from app.agents.dna_agent import DNAAgent


def test_composition_schema_and_presets():
    """Verify Creatomate-style composition schema and built-in template presets."""
    preset = TEMPLATE_PRESETS["fast_news_explainer"]
    assert preset.aspect_ratio == "9:16"
    assert preset.default_progress_style == ProgressIndicatorStyle.BOTTOM_BAR
    assert preset.animation == AnimationType.KEN_BURNS

    # Construct full composition
    scene1 = CompositionScene(
        scene_number=1,
        duration=5.0,
        headline="AI Agents Reality Check",
        narration="Most AI agent demos fail in production.",
        image_path="/tmp/fake_image.jpg",
        audio_path="/tmp/fake_audio.wav",
        elements=[
            TemplateElement(
                track_type=TrackType.HOOK,
                content_text="Stop deploying broken agents!",
                animation=AnimationType.POP,
            ),
            TemplateElement(
                track_type=TrackType.HEADLINE,
                content_text="AI Agents Reality Check",
                font_size=48,
            ),
        ],
    )

    comp = ContentComposition(
        title="AI Agents in 2026",
        template_variant="fast_news_explainer",
        progress_style=ProgressIndicatorStyle.BOTTOM_BAR,
        scenes=[scene1],
    )

    assert len(comp.scenes) == 1
    assert comp.scenes[0].elements[0].track_type == TrackType.HOOK
    assert comp.template_variant == "fast_news_explainer"
    assert comp.width == 1080
    assert comp.height == 1920


def test_composition_engine_ffmpeg_filters():
    """Verify deterministic FFmpeg filter chains for Ken Burns, headlines, and dynamic progress bars."""
    engine = CompositionEngine(output_dir="/tmp/test_composition")
    
    scene = CompositionScene(
        scene_number=1,
        duration=6.0,
        headline="Production AI Architecture",
        narration="Here is how to structure your worker queue.",
        image_path="/tmp/img.png",
        audio_path="/tmp/audio.wav",
    )

    comp = ContentComposition(
        title="Production AI Architecture",
        template_variant="fast_news_explainer",
        progress_style=ProgressIndicatorStyle.BOTTOM_BAR,
        progress_color="#FF3B30",
        scenes=[scene],
    )

    filters = engine.build_scene_video_filters(
        scene=scene,
        composition=comp,
        scene_duration=6.0,
    )

    filter_str = ",".join(filters)
    # Check resolution
    assert "scale=1080:1920" in filter_str
    # Check Ken Burns zoompan
    assert "zoompan=" in filter_str
    # Check headline banner
    assert "drawbox=" in filter_str
    assert "drawtext=" in filter_str
    assert "Production AI Architecture" in filter_str
    # Check dynamic progress bar growing over time
    assert "t/6.0" in filter_str
    assert "#FF3B30" in filter_str


def test_composition_engine_top_bar_and_hormozi_style():
    """Verify top progress bar and Hormozi bold template configuration."""
    engine = CompositionEngine(output_dir="/tmp/test_composition")
    scene = CompositionScene(
        scene_number=2,
        duration=4.5,
        headline="Crucial Step 2",
        image_path="/tmp/img.png",
        audio_path="/tmp/audio.wav",
    )
    comp = ContentComposition(
        title="Fast Growth Tips",
        template_variant="hormozi_bold",
        progress_style=ProgressIndicatorStyle.TOP_BAR,
        progress_color="#FFCC00",
        scenes=[scene],
    )

    filters = engine.build_scene_video_filters(scene, comp, 4.5)
    filter_str = ",".join(filters)
    assert "drawbox=x=0:y=0:w='min(w, (t/4.5)*w)':h=14:color=#FFCC00@0.9:t=fill" in filter_str


def test_video_service_composition_interface():
    """Verify VideoService exposes create_composition_video method."""
    svc = VideoService()
    assert hasattr(svc, "create_composition_video")
    assert callable(svc.create_composition_video)


@pytest.mark.asyncio
async def test_content_dna_synthesis_and_defaults():
    """Verify ContentDNA contracts, validation, and negative constraints."""
    dna = ContentDNA(
        topic="Self-Hosted LLMs",
        target_audience="Backend Developers",
        brand_archetype=BrandArchetype.TACTICAL_BUILDER,
        voice_tone=VoiceTone.CONCISE_PUNCHY,
        visual_aesthetic=VisualAesthetic.DARK_TECH_CINEMATIC,
        hook_philosophy=HookPhilosophy.CONTRARIAN_MYTHBUSTER,
    )

    assert dna.topic == "Self-Hosted LLMs"
    assert dna.brand_archetype == BrandArchetype.TACTICAL_BUILDER
    assert len(dna.negative_rules) >= 2
    assert any("buzzwords" in rule.lower() for rule in dna.negative_rules)

    agent = DNAAgent()
    generated_dna = await agent.generate_dna(
        topic="Autonomous Coding Agents",
        audience="Principal Architects",
    )
    assert generated_dna.topic == "Autonomous Coding Agents"
    assert generated_dna.target_audience == "Principal Architects"
    assert generated_dna.brand_archetype is not None


@pytest.mark.asyncio
async def test_dna_batch_expansion_diversity():
    """Verify DNA expansion generates distinct non-overlapping angles rather than clone videos."""
    agent = DNAAgent()
    dna = ContentDNA(
        topic="Distributed Video Rendering",
        target_audience="DevOps & Media Engineers",
        brand_archetype=BrandArchetype.EDUCATIONAL_AUTHORITY,
        hook_philosophy=HookPhilosophy.CONTRARIAN_MYTHBUSTER,
    )

    plan: BatchDNAPlan = await agent.expand_dna_batch(dna=dna, count=4)
    assert plan.total_count == 4
    assert len(plan.variations) == 4

    # Ensure variations have unique angle types
    angle_types = [v.angle_type for v in plan.variations]
    assert len(set(angle_types)) >= 3  # At least 3 distinct framework angles

    # Ensure differentiators and avoid_overlap constraints are present
    for var in plan.variations:
        assert var.title
        assert var.hook_text
        assert var.differentiator
        assert len(var.avoid_overlap_with) > 0
        assert var.recommended_template in TEMPLATE_PRESETS
