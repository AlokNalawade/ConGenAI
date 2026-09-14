"""Unit tests for Superpowers Phase A: Audio & Visual Pacing."""

import pytest
import os
import tempfile
from app.services.kinetic_subtitle_service import (
    KineticSubtitleService,
    KineticSubtitleResult,
    SoundCue,
)
from app.services.pacing_optimizer import PacingOptimizerService
from app.templates.composition_engine import CompositionEngine


def test_kinetic_subtitle_emoji_and_sfx_detection():
    """Verify Submagic-style keyword emoji detection and SFX cue generation."""
    assert KineticSubtitleService.detect_keyword_emoji("money") == "💸"
    assert KineticSubtitleService.detect_keyword_emoji("profit") == "📈"
    assert KineticSubtitleService.detect_keyword_emoji("crashed") == "📉"
    assert KineticSubtitleService.detect_keyword_emoji("secret") == "🤫"
    assert KineticSubtitleService.detect_keyword_emoji("growth") == "🚀"

    with tempfile.TemporaryDirectory() as tmpdir:
        ass_path = os.path.join(tmpdir, "test_kinetic.ass")
        script = "Why most AI startups lose money and crash in production"
        res: KineticSubtitleResult = KineticSubtitleService.generate_kinetic_ass(
            text=script,
            duration=5.0,
            output_path=ass_path,
        )

        assert os.path.exists(res.ass_file_path)
        assert res.injected_emoji_count >= 2  # money and crash
        assert len(res.sfx_cues) >= 2

        # Check SFX cues have timestamps
        for cue in res.sfx_cues:
            assert cue.timestamp >= 0.0
            assert cue.sfx_name in ["cash", "glitch", "pop", "whoosh"]

        with open(res.ass_file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "💸" in content
            assert "📉" in content

            # Verify rhythmic bursts (2-4 words per dialogue event rather than repeating full sentence)
            import re
            dialogue_lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
            assert len(dialogue_lines) > 0
            for dl in dialogue_lines:
                clean_dl = re.sub(r"\{.*?\}", "", dl.split(",,", 1)[-1])
                words_in_line = clean_dl.split()
                assert len(words_in_line) <= 5, f"Expected rhythmic burst, got {len(words_in_line)} words: {clean_dl}"


def test_pacing_optimizer_silence_and_zoom_filters():
    """Verify CapCut-style silence removal filter and 3-second attention reset punch-in filter."""
    silence_filter = PacingOptimizerService.get_silence_removal_filter(
        min_silence_duration=0.25,
        silence_threshold_db="-35dB",
    )
    assert "silenceremove" in silence_filter
    assert "stop_duration=0.25" in silence_filter
    assert "stop_threshold=-35dB" in silence_filter

    zoom_filter = PacingOptimizerService.get_punch_in_zoom_filter(
        interval_seconds=3.0,
        zoom_factor=1.12,
        width=1080,
        height=1920,
    )
    assert "zoompan=" in zoom_filter
    assert "1.12" in zoom_filter
    assert "1080x1920" in zoom_filter
    assert "between(mod(it,6.0),3.0,6.0)" in zoom_filter


def test_dynamic_audio_ducking_filter():
    """Verify ElevenLabs-style dynamic sidechain audio ducking filter construction."""
    duck_filter = CompositionEngine.build_audio_ducking_filter(music_volume=0.15, ducking_ratio=6.0)
    assert "sidechaincompress=" in duck_filter
    assert "ratio=6.0" in duck_filter
    assert "volume=0.15" in duck_filter
