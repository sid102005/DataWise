"""Unit tests for VideoProcessor (Branch A: Full Video Processing with FFmpeg)."""

import json
from pathlib import Path
from PIL import Image
import pytest

from backend.processors.video import VideoProcessor, is_ffmpeg_available
from backend.core.exceptions import ExecutionError, FileValidationError
from backend.models.schemas import Step, Plan

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "video"
SAMPLE_MP4 = FIXTURES_DIR / "sample.mp4"
VIDEO_EXPECTED = FIXTURES_DIR / "expected_values.json"


@pytest.fixture
def processor() -> VideoProcessor:
    return VideoProcessor()


def test_video_processor_profile_metadata(processor: VideoProcessor):
    """profile() extracts container format, duration, resolution and codecs via ffprobe."""
    assert SAMPLE_MP4.exists()
    profile = processor.profile(SAMPLE_MP4)
    expected = json.loads(VIDEO_EXPECTED.read_text(encoding="utf-8"))["sample.mp4"]

    assert profile["file_format"] == "mp4"
    assert profile["duration_seconds"] == expected["duration_seconds"]
    assert profile["width"] == expected["width"]
    assert profile["height"] == expected["height"]
    assert "metadata" in profile
    assert profile["metadata"]["video_codec"] == expected["video_codec"]


def test_video_processor_validate_input(processor: VideoProcessor):
    """validate_input() accepts video extensions and rejects unsupported ones."""
    ok, _ = processor.validate_input(SAMPLE_MP4)
    assert ok is True

    fake_file = SAMPLE_MP4.parent / "non_existent.mp4"
    ok, msg = processor.validate_input(fake_file)
    assert ok is False

    txt_file = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "documents" / "sample.txt"
    if txt_file.exists():
        ok, msg = processor.validate_input(txt_file)
        assert ok is False


def test_video_processor_execute_metadata(processor: VideoProcessor):
    """Executing extract_metadata step produces full stream metadata summary."""
    step = Step(
        step_number=1,
        tool_name="extract_metadata",
        description="Extract video metadata",
        parameters={},
        expected_output="Video metadata extracted",
    )
    result = processor.execute(SAMPLE_MP4, step)
    assert isinstance(result, dict)
    assert result["file_format"] == "mp4"
    assert result["duration_seconds"] == 3.0
    assert result["width"] == 320
    assert result["height"] == 240
    assert len(result["step_results"]) == 1
    assert result["step_results"][0].success is True


def test_video_processor_execute_trim(processor: VideoProcessor):
    """Executing trim operation cuts video duration using FFmpeg."""
    if is_ffmpeg_available():
        step = Step(
            step_number=1,
            tool_name="trim",
            description="Trim video to 1.5 seconds",
            parameters={"start_seconds": 0.0, "end_seconds": 1.5},
            expected_output="Video trimmed",
        )
        result = processor.execute(SAMPLE_MP4, step)
        assert result["duration_seconds"] <= 1.6
        trimmed_file = Path(result["source_file"])
        assert trimmed_file.exists()

        plan = Plan(plan_id="p1", session_id="s1", objectives=[], steps=[step], rationale="test")
        val = processor.validate_output(
            before_state=SAMPLE_MP4,
            after_state=result,
            structured_operation=plan,
        )
        assert val.is_valid is True
        assert "video_trimmed_verified" in val.checks_passed


def test_video_processor_execute_resize(processor: VideoProcessor):
    """Executing resize operation scales video dimensions using FFmpeg."""
    if is_ffmpeg_available():
        step = Step(
            step_number=1,
            tool_name="resize",
            description="Resize video to 160x120",
            parameters={"width": 160, "height": 120},
            expected_output="Video resized",
        )
        result = processor.execute(SAMPLE_MP4, step)
        assert result["width"] == 160
        assert result["height"] == 120
        resized_file = Path(result["source_file"])
        assert resized_file.exists()

        plan = Plan(plan_id="p2", session_id="s2", objectives=[], steps=[step], rationale="test")
        val = processor.validate_output(
            before_state=SAMPLE_MP4,
            after_state=result,
            structured_operation=plan,
        )
        assert val.is_valid is True
        assert "video_resized_verified" in val.checks_passed


def test_video_processor_execute_extract_frame(processor: VideoProcessor):
    """Executing extract_frame extracts a PNG frame at timestamp using FFmpeg."""
    if is_ffmpeg_available():
        step = Step(
            step_number=1,
            tool_name="extract_frame",
            description="Extract video frame at 1.0s",
            parameters={"timestamp_seconds": 1.0},
            expected_output="Video frame extracted",
        )
        result = processor.execute(SAMPLE_MP4, step)
        frame_file = Path(result["source_file"])
        assert frame_file.exists()

        with Image.open(frame_file) as im:
            assert im.width == 320
            assert im.height == 240

        plan = Plan(plan_id="p3", session_id="s3", objectives=[], steps=[step], rationale="test")
        val = processor.validate_output(
            before_state=SAMPLE_MP4,
            after_state=result,
            structured_operation=plan,
        )
        assert val.is_valid is True
        assert "video_frame_verified" in val.checks_passed


def test_video_processor_validate_output_success(processor: VideoProcessor):
    """validate_output() succeeds when metadata matches the source file on disk."""
    step = Step(
        step_number=1,
        tool_name="extract_metadata",
        description="Extract video metadata",
        parameters={},
        expected_output="Video metadata extracted",
    )
    plan = Plan(
        plan_id="video_plan",
        session_id="video_session",
        objectives=[],
        steps=[step],
        rationale="testing",
    )
    after_state = {
        "duration_seconds": 3.0,
        "width": 320,
        "height": 240,
    }
    val = processor.validate_output(
        before_state=SAMPLE_MP4,
        after_state=after_state,
        structured_operation=plan,
    )
    assert val.is_valid is True
    assert "video_metadata_extracted" in val.checks_passed
    assert "video_metadata_verified" in val.checks_passed


def test_video_processor_validate_output_deliberately_wrong(processor: VideoProcessor):
    """validate_output() fails when claimed duration does not match source file."""
    step = Step(
        step_number=1,
        tool_name="extract_metadata",
        description="Extract video metadata",
        parameters={},
        expected_output="Video metadata extracted",
    )
    plan = Plan(
        plan_id="video_plan",
        session_id="video_session",
        objectives=[],
        steps=[step],
        rationale="testing",
    )
    fraudulent_after_state = {
        "duration_seconds": 15.0,  # Claiming 15s for 3.0s file
        "width": 320,
        "height": 240,
    }
    val = processor.validate_output(
        before_state=SAMPLE_MP4,
        after_state=fraudulent_after_state,
        structured_operation=plan,
    )
    assert val.is_valid is False
    assert "video_metadata_verification_failed" in val.checks_failed
