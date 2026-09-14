"""Unit tests for Superpowers Phase B: Media & Computer Vision."""

import pytest
import os
import tempfile
from PIL import Image, ImageDraw
from app.services.broll_service import BRollService, BRollClip
from app.services.auto_reframe import AutoReframeService, CropCoordinates
from app.services.visual_dna_service import VisualDNAService, STYLE_PACKS


def test_broll_service_semantic_matching():
    """Verify InVideo-style stock B-roll semantic matching."""
    service = BRollService()

    # Query matching servers
    match_server = service.match_broll("A dark datacenter with glowing server racks and cloud infrastructure")
    assert match_server is not None
    assert match_server.id == "broll_server_01"
    assert match_server.relevance_score >= 0.6

    # Query matching finance
    match_finance = service.match_broll("Stock market candlestick charts showing trading profit and loss")
    assert match_finance is not None
    assert match_finance.id == "broll_finance_04"
    assert match_finance.relevance_score >= 0.6

    # Decision threshold check
    should_use, clip = service.should_use_broll("High performance database server clusters")
    assert should_use is True
    assert clip is not None

    should_not_use, _ = service.should_use_broll("A fantasy wizard casting magic spells in a forest")
    assert should_not_use is False


def test_auto_reframe_saliency_and_crop():
    """Verify Opus Clip-style saliency focal-point calculation and vertical reframing."""
    # Create a 1920x1080 horizontal image with an asymmetric high-contrast shape on the right
    img = Image.new("RGB", (1920, 1080), color=(10, 10, 10))
    draw = ImageDraw.Draw(img)
    # Draw high contrast white box in right quadrant (x=1400, y=400)
    draw.rectangle([1300, 300, 1600, 700], fill=(255, 255, 255))

    crop: CropCoordinates = AutoReframeService.calculate_vertical_crop(img, target_aspect_ratio=9.0/16.0)
    # Crop target width is 1080 * 0.5625 = ~607px
    assert crop.target_width == int(1080 * (9.0/16.0))
    # Focal point should be biased to the right (>960)
    assert crop.focal_x > 960
    assert crop.left > 600

    # Test full image reframing to file
    with tempfile.TemporaryDirectory() as tmpdir:
        input_path = os.path.join(tmpdir, "input.png")
        output_path = os.path.join(tmpdir, "output_916.png")
        img.save(input_path)

        AutoReframeService.reframe_image(input_path, output_path, target_resolution=(1080, 1920))
        assert os.path.exists(output_path)
        out_img = Image.open(output_path)
        assert out_img.size == (1080, 1920)


def test_visual_dna_style_packs_and_locks():
    """Verify Runway-style visual consistency packs and negative prompt locks."""
    assert "dark_tech_cyberpunk" in STYLE_PACKS
    assert "minimal_monochrome" in STYLE_PACKS

    decorated = VisualDNAService.decorate_prompt(
        base_prompt="A developer reviewing code terminal on workstation",
        style_pack_name="dark_tech_cyberpunk",
        custom_negative="extra fingers",
    )

    assert "cinematic film still" in decorated["positive_prompt"]
    assert "A developer reviewing code terminal on workstation" in decorated["positive_prompt"]
    assert "octane render" in decorated["positive_prompt"]
    assert "cartoon" in decorated["negative_prompt"]
    assert "extra fingers" in decorated["negative_prompt"]
    assert decorated["seed"] == 1337


def test_broll_anti_repetition_and_usage_tracking():
    """Verify that BRollService penalizes recently and frequently used clips to prevent repetition."""
    BRollService.reset_usage()
    service = BRollService()

    # First match should have full relevance score
    clip1 = service.match_broll("datacenter cloud server infrastructure")
    assert clip1 is not None
    assert clip1.id == "broll_server_01"
    initial_score = clip1.relevance_score
    assert initial_score > 0.5

    # Simulate using it in a scene
    service.record_usage(clip1.id)

    # Immediately matching again should be penalized due to recency
    clip2 = service.match_broll("datacenter cloud server infrastructure")
    assert clip2 is not None
    assert clip2.relevance_score < initial_score

    # Repeated usage should further penalize score
    for _ in range(5):
        service.record_usage("broll_server_01")
    clip3 = service.match_broll("datacenter cloud server infrastructure")
    assert clip3.relevance_score < 0.3
