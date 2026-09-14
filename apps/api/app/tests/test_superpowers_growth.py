"""Unit tests for Superpowers Phase C: Growth Packaging & Mobile Thumbnails."""

import pytest
import os
import tempfile
from PIL import Image
from app.services.thumbnail_generator import (
    ThumbnailGeneratorService,
    ThumbnailStyle,
    ThumbnailCandidate,
)


def test_3way_thumbnail_candidate_generation():
    """Verify VidIQ-style 3-way mobile thumbnail generation across all 3 styles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a base image
        base_path = os.path.join(tmpdir, "base_scene.png")
        base_img = Image.new("RGB", (1080, 1920), color=(20, 25, 35))
        base_img.save(base_path)

        generator = ThumbnailGeneratorService(output_dir=os.path.join(tmpdir, "thumbs"))
        candidates = generator.generate_3way_thumbnails(
            base_image_path=base_path,
            headline="Why AI Pipelines Crash",
            stat_or_warning="⚠️ STOP RETRYING",
        )

        assert len(candidates) == 3
        styles = [c.style for c in candidates]
        assert ThumbnailStyle.CURIOSITY_HOOK in styles
        assert ThumbnailStyle.WARNING_ALERT in styles
        assert ThumbnailStyle.STATISTIC_PROOF in styles

        for cand in candidates:
            assert os.path.exists(cand.image_path)
            cand_img = Image.open(cand.image_path)
            assert cand_img.size == (1080, 1920)
            assert cand.headline_text == "Why AI Pipelines Crash"
            assert cand.badge_text is not None


def test_thumbnail_evidence_integrity_and_platform_resolutions():
    """Verify evidence integrity (no fabricated 90% FAIL) and YouTube 16:9 resolution support."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = os.path.join(tmpdir, "base_scene.png")
        base_img = Image.new("RGB", (1280, 720), color=(15, 20, 30))
        base_img.save(base_path)

        generator = ThumbnailGeneratorService(output_dir=os.path.join(tmpdir, "thumbs"))

        # Case A: No verified stats provided -> should NOT fabricate "90% FAIL"
        candidates_unverified = generator.generate_3way_thumbnails(
            base_image_path=base_path,
            headline="Scaling Postgres to 10k QPS",
            target_resolution=(1280, 720),
        )
        for c in candidates_unverified:
            assert c.badge_text != "90% FAIL"
            cand_img = Image.open(c.image_path)
            assert cand_img.size == (1280, 720)

        # Case B: Verified statistic provided from research -> should accurately display it
        candidates_verified = generator.generate_3way_thumbnails(
            base_image_path=base_path,
            headline="Scaling Postgres to 10k QPS",
            verified_statistic="73% FASTER WITH INDEX",
            target_resolution=(1280, 720),
        )
        stat_candidate = next(c for c in candidates_verified if c.style == ThumbnailStyle.STATISTIC_PROOF)
        assert stat_candidate.badge_text == "73% FASTER WITH INDEX"
