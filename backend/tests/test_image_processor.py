"""Comprehensive tests for ImageProcessor in backend/processors/image.py."""

import json
from pathlib import Path
from PIL import Image
import pytest

from backend.core.exceptions import FileValidationError
from backend.models.schemas import Plan, Step, ValidationResult
from backend.processors.image import ImageProcessor

FIXTURES_DIR = Path("tests/fixtures/images")
EXPECTED = json.loads((FIXTURES_DIR / "expected_values.json").read_text(encoding="utf-8"))


@pytest.fixture
def image_proc():
    return ImageProcessor()


def create_plan(tool_name: str, parameters: dict = None) -> Plan:
    return Plan(
        plan_id="p-img-1",
        session_id="s-img-1",
        objectives=[],
        steps=[
            Step(
                step_number=1,
                tool_name=tool_name,
                description=f"Run {tool_name}",
                parameters=parameters or {},
                expected_output="Success",
            )
        ],
    )


def test_profile_formats(image_proc):
    """Verify profile() extracts correct dimensions and format for all 6 image formats."""
    for filename in ["sample.jpg", "sample.png", "sample.gif", "sample.bmp", "sample.webp", "sample.tiff"]:
        path = FIXTURES_DIR / filename
        prof = image_proc.profile(path)
        exp = EXPECTED[filename]
        assert prof["width"] == exp["width"]
        assert prof["height"] == exp["height"]
        assert prof["color_mode"] == exp["mode"]
        assert prof["file_size"] > 0


def test_security_decompression_bomb_rejected(image_proc):
    """Verify that a crafted decompression bomb image is rejected rather than silently processed."""
    bomb_path = FIXTURES_DIR / "bomb_image.png"
    # 1. validate_input returns False
    is_valid, err = image_proc.validate_input(bomb_path)
    assert is_valid is False
    assert "Decompression bomb" in err or "maximum pixel limit" in err

    # 2. profile raises FileValidationError
    with pytest.raises(FileValidationError) as exc:
        image_proc.profile(bomb_path)
    assert "Decompression bomb" in str(exc.value) or "maximum pixel limit" in str(exc.value)


def test_security_decompression_bomb_guard_not_disabled():
    """Verify that MAX_IMAGE_PIXELS protection is active and not set to None."""
    assert Image.MAX_IMAGE_PIXELS is not None
    assert Image.MAX_IMAGE_PIXELS > 0


def test_malformed_image_rejected(image_proc):
    """Verify that a corrupted image stream fails gracefully with an honest message."""
    malformed_path = FIXTURES_DIR / "malformed_image.jpg"
    is_valid, err = image_proc.validate_input(malformed_path)
    assert is_valid is False
    assert "Invalid or corrupted image" in err

    with pytest.raises(FileValidationError) as exc:
        image_proc.profile(malformed_path)
    assert "File is not a valid or readable image" in str(exc.value)


def test_resize_operation(image_proc, tmp_path):
    """Verify resize() resizes to exact requested dimensions and validate_output() passes."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("resize", {"width": 1024, "height": 1024})
    result = image_proc.execute(file_path, plan)

    # 1. Verify in-memory result dimensions
    img = result["image"]
    assert img.size == (1024, 1024)

    # 2. Verify validation output has named checks
    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "resize_dimensions_exact: 1024x1024" in validation.checks_passed

    # 3. Export to disk and verify reopened file dimensions
    out_file = image_proc.export(result, "jpg", tmp_path)
    assert out_file.exists()
    with Image.open(out_file) as reopened:
        assert reopened.size == (1024, 1024)


def test_crop_operation(image_proc, tmp_path):
    """Verify crop() crops to exact requested bounding box and output size matches."""
    file_path = FIXTURES_DIR / "sample.png"
    plan = create_plan("crop", {"left": 50, "top": 50, "right": 450, "bottom": 350})
    result = image_proc.execute(file_path, plan)

    img = result["image"]
    assert img.size == (400, 300)

    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "crop_dimensions_exact: 400x300" in validation.checks_passed

    out_file = image_proc.export(result, "png", tmp_path)
    with Image.open(out_file) as reopened:
        assert reopened.size == (400, 300)


def test_rotate_90_with_corner_marker(image_proc):
    """Verify 90-degree rotation swaps dimensions and shifts the top-left red marker to bottom-left."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("rotate", {"degrees": 90})
    result = image_proc.execute(file_path, plan)

    # Original is 800x600 -> Rotated is 600x800
    img = result["image"]
    assert img.size == (600, 800)

    # Verify content: top-left was red, should now be at bottom-left
    p_bl = img.convert("RGB").getpixel((10, 790))
    assert p_bl[0] > 200 and p_bl[1] < 50 and p_bl[2] < 50

    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "rotate_90_dimensions_swapped: 600x800" in validation.checks_passed
    assert any("red marker moved to bottom-left" in c for c in validation.checks_passed)


def test_rotate_180_with_corner_marker(image_proc):
    """Verify 180-degree rotation preserves dimensions and moves marker to bottom-right."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("rotate", {"degrees": 180})
    result = image_proc.execute(file_path, plan)

    img = result["image"]
    assert img.size == (800, 600)

    p_br = img.convert("RGB").getpixel((790, 590))
    assert p_br[0] > 200 and p_br[1] < 50 and p_br[2] < 50

    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "rotate_180_dimensions_preserved: 800x600" in validation.checks_passed
    assert any("red marker moved to bottom-right" in c for c in validation.checks_passed)


def test_rotate_270_with_corner_marker(image_proc):
    """Verify 270-degree rotation swaps dimensions and moves marker to top-right."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("rotate", {"degrees": 270})
    result = image_proc.execute(file_path, plan)

    img = result["image"]
    assert img.size == (600, 800)

    p_tr = img.convert("RGB").getpixel((590, 10))
    assert p_tr[0] > 200 and p_tr[1] < 50 and p_tr[2] < 50

    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "rotate_270_dimensions_swapped: 600x800" in validation.checks_passed
    assert any("red marker moved to top-right" in c for c in validation.checks_passed)


def test_convert_format(image_proc, tmp_path):
    """Verify real format conversion: output format is validated via Pillow format detection, not just extension."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("convert_format", {"target_format": "png"})
    result = image_proc.execute(file_path, plan)

    out_file = image_proc.export(result, "png", tmp_path)
    assert out_file.exists()

    with Image.open(out_file) as reopened:
        assert reopened.format == "PNG"

    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "convert_format_verified: target=PNG" in validation.checks_passed


def test_compress_operation(image_proc, tmp_path):
    """Verify compression reduces file size versus higher quality input on lossy format."""
    file_path = FIXTURES_DIR / "sample.jpg"
    original_size = file_path.stat().st_size

    # Compress with quality 30
    plan = create_plan("compress", {"quality": 30})
    result = image_proc.execute(file_path, plan)
    out_file = image_proc.export(result, "jpg", tmp_path)

    compressed_size = out_file.stat().st_size
    assert compressed_size < original_size

    validation = image_proc.validate_output(file_path, result, plan, export_path=out_file)
    assert validation.is_valid is True
    assert any("compression_verified" in c for c in validation.checks_passed)


def test_extract_metadata(image_proc):
    """Verify metadata extraction returns dimensions, format, and mode."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("extract_metadata")
    result = image_proc.execute(file_path, plan)

    assert "metadata" in result
    meta = result["metadata"]
    assert meta["width"] == 800
    assert meta["height"] == 600
    assert meta["color_mode"] == "RGB"

    validation = image_proc.validate_output(file_path, result, plan)
    assert validation.is_valid is True
    assert "metadata_extracted: true" in validation.checks_passed


def test_extract_text_ocr_gating(image_proc):
    """Verify OCR raises an explicit unsupported error when Tesseract binary is not installed."""
    file_path = FIXTURES_DIR / "sample.jpg"
    plan = create_plan("extract_text_ocr")
    with pytest.raises(ValueError) as exc:
        image_proc.execute(file_path, plan)
    assert "OCR is not supported" in str(exc.value)


def test_validation_failure_deliberately_wrong(image_proc):
    """Prove that a deliberately-wrong output state fails validation with a clear error."""
    file_path = FIXTURES_DIR / "sample.jpg"
    # Plan requests resize to 500x500
    plan = create_plan("resize", {"width": 500, "height": 500})

    # But we provide an image that is 800x600
    with Image.open(file_path) as raw_img:
        bad_result = {"image": raw_img.copy()}

    validation = image_proc.validate_output(file_path, bad_result, plan)
    assert validation.is_valid is False
    assert len(validation.checks_failed) > 0
    assert "resize dimension mismatch: expected (500x500), got (800x600)" in validation.checks_failed[0]
