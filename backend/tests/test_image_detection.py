"""Tests for Image format detection and spoofing rejection."""

from pathlib import Path
import pytest

from backend.core.file_detection import detect_file, FileCategory
from backend.processors.registry import get_processor
from backend.processors.image import ImageProcessor

FIXTURES_DIR = Path("tests/fixtures/images")


def test_detect_jpeg():
    res = detect_file(FIXTURES_DIR / "sample.jpg")
    assert res.detected_category == FileCategory.IMAGE
    assert res.magic_signature_category == FileCategory.IMAGE
    assert res.confidence == 1.0


def test_detect_png():
    res = detect_file(FIXTURES_DIR / "sample.png")
    assert res.detected_category == FileCategory.IMAGE
    assert res.magic_signature_category == FileCategory.IMAGE
    assert res.confidence == 1.0


def test_detect_gif():
    res = detect_file(FIXTURES_DIR / "sample.gif")
    assert res.detected_category == FileCategory.IMAGE
    assert res.magic_signature_category == FileCategory.IMAGE
    assert res.confidence == 1.0


def test_detect_bmp():
    res = detect_file(FIXTURES_DIR / "sample.bmp")
    assert res.detected_category == FileCategory.IMAGE
    assert res.magic_signature_category == FileCategory.IMAGE
    assert res.confidence == 1.0


def test_detect_webp():
    res = detect_file(FIXTURES_DIR / "sample.webp")
    assert res.detected_category == FileCategory.IMAGE
    assert res.magic_signature_category == FileCategory.IMAGE
    assert res.confidence == 1.0


def test_detect_tiff():
    res = detect_file(FIXTURES_DIR / "sample.tiff")
    assert res.detected_category == FileCategory.IMAGE
    assert res.magic_signature_category == FileCategory.IMAGE
    assert res.confidence == 1.0


def test_detect_extension_spoofing_caught():
    """Verify that a text file renamed to .jpg is caught via magic bytes."""
    fake_image = FIXTURES_DIR / "fake_image.jpg"
    res = detect_file(fake_image)
    # Magic bytes sniff tabular/text, NOT image
    assert res.magic_signature_category != FileCategory.IMAGE
    assert res.detected_category != FileCategory.IMAGE
    # ImageProcessor input validation also rejects it cleanly without crashing
    processor = ImageProcessor()
    is_valid, err = processor.validate_input(fake_image)
    assert is_valid is False
    assert "Invalid or corrupted image" in err


def test_image_registry():
    """Verify ImageProcessor is registered for FileCategory.IMAGE."""
    proc = get_processor(FileCategory.IMAGE)
    assert isinstance(proc, ImageProcessor)
