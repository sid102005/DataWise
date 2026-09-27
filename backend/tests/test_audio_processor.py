"""Unit tests for AudioProcessor (Branch A: Full Audio Processing with FFmpeg)."""

import json
from pathlib import Path
import pytest

from backend.processors.audio import AudioProcessor, is_ffmpeg_available
from backend.core.exceptions import FileValidationError, ExecutionError
from backend.models.schemas import Step, Plan

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
SAMPLE_WAV = FIXTURES_DIR / "audio" / "sample.wav"
AUDIO_EXPECTED = FIXTURES_DIR / "audio" / "expected_values.json"


@pytest.fixture
def processor() -> AudioProcessor:
    return AudioProcessor()


def test_audio_processor_metadata_extraction(processor: AudioProcessor):
    """AudioProcessor.profile extracts real metadata matching expected_values.json."""
    assert SAMPLE_WAV.exists()
    profile = processor.profile(SAMPLE_WAV)
    expected = json.loads(AUDIO_EXPECTED.read_text(encoding="utf-8"))["sample.wav"]

    assert profile["file_format"] == "wav"
    assert profile["duration_seconds"] == expected["duration_seconds"]
    assert profile["sample_rate"] == expected["sample_rate"]
    assert profile["channels"] == expected["channels"]
    assert profile["sample_width"] == expected["sample_width"]


def test_audio_processor_validate_input(processor: AudioProcessor):
    """validate_input accepts supported extensions and rejects unsupported ones."""
    ok, _ = processor.validate_input(SAMPLE_WAV)
    assert ok is True

    fake_file = SAMPLE_WAV.parent / "non_existent.wav"
    ok, msg = processor.validate_input(fake_file)
    assert ok is False

    txt_file = FIXTURES_DIR / "documents" / "sample.txt"
    if txt_file.exists():
        ok, msg = processor.validate_input(txt_file)
        assert ok is False


def test_audio_processor_execute_metadata(processor: AudioProcessor):
    """Executing extract_metadata step produces metadata dictionary."""
    step = Step(
        step_number=1,
        tool_name="extract_metadata",
        description="Extract audio metadata",
        parameters={},
        expected_output="Audio metadata extracted",
    )
    result = processor.execute(SAMPLE_WAV, step)
    assert isinstance(result, dict)
    assert result["duration_seconds"] == 3.0
    assert result["sample_rate"] == 44100
    assert result["channels"] == 2


def test_audio_processor_execute_trim_real(processor: AudioProcessor, tmp_path: Path):
    """Executing real trim operation trims audio to 1.5 seconds via FFmpeg."""
    if is_ffmpeg_available():
        step = Step(
            step_number=1,
            tool_name="trim",
            description="Trim audio to 1.5 seconds",
            parameters={"start_seconds": 0.0, "end_seconds": 1.5},
            expected_output="Audio trimmed",
        )
        result = processor.execute(SAMPLE_WAV, step)
        assert result["duration_seconds"] <= 1.6
        trimmed_file = Path(result["source_file"])
        assert trimmed_file.exists()
        # Verify validate_output on trimmed file
        plan = Plan(plan_id="p1", session_id="s1", objectives=[], steps=[step], rationale="test")
        val = processor.validate_output(
            before_state=SAMPLE_WAV,
            after_state=result,
            structured_operation=plan,
        )
        assert val.is_valid is True
        assert "audio_trimmed_verified" in val.checks_passed


def test_audio_processor_export(processor: AudioProcessor, tmp_path: Path):
    """export creates valid audio file output in output directory."""
    state = {"source_file": str(SAMPLE_WAV)}
    out_file = processor.export(state, output_format="wav", output_dir=tmp_path, filename_stem="result")
    assert out_file.exists()
    assert out_file.name == "result.wav"
    assert out_file.stat().st_size == SAMPLE_WAV.stat().st_size


def test_audio_processor_validate_output_success(processor: AudioProcessor):
    """validate_output independently confirms audio metadata matches ground truth."""
    step = Step(
        step_number=1,
        tool_name="extract_metadata",
        description="Extract audio metadata",
        parameters={},
        expected_output="Audio metadata extracted",
    )
    plan = Plan(
        plan_id="test_plan",
        session_id="test_session",
        objectives=[],
        steps=[step],
        rationale="testing",
    )
    after_state = {
        "duration_seconds": 3.0,
        "sample_rate": 44100,
        "channels": 2,
    }
    val = processor.validate_output(
        before_state=SAMPLE_WAV,
        after_state=after_state,
        structured_operation=plan,
    )
    assert val.is_valid is True
    assert "audio_metadata_extracted" in val.checks_passed
    assert "audio_metadata_verified" in val.checks_passed
    assert len(val.checks_failed) == 0


def test_audio_processor_validate_output_deliberately_wrong(processor: AudioProcessor):
    """validate_output fails when claimed duration does not match actual duration."""
    step = Step(
        step_number=1,
        tool_name="extract_metadata",
        description="Extract audio metadata",
        parameters={},
        expected_output="Audio metadata extracted",
    )
    plan = Plan(
        plan_id="test_plan",
        session_id="test_session",
        objectives=[],
        steps=[step],
        rationale="testing",
    )
    # Deliberately falsified duration (claimed 10.5s instead of actual 3.0s)
    fraudulent_after_state = {
        "duration_seconds": 10.5,
        "sample_rate": 44100,
        "channels": 2,
    }
    val = processor.validate_output(
        before_state=SAMPLE_WAV,
        after_state=fraudulent_after_state,
        structured_operation=plan,
    )
    assert val.is_valid is False
    assert "audio_metadata_verification_failed" in val.checks_failed
