"""Unit tests for Video magic-byte detection and registry routing (Phase 12)."""

from pathlib import Path
import pytest

from backend.core.file_detection import detect_file, FileCategory
from backend.processors.registry import get_processor, UnsupportedFileTypeError
from backend.processors.video import VideoProcessor

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "video"


def test_detect_legitimate_mp4():
    """Minimal MP4 header (ftypmp42) detects as FileCategory.VIDEO."""
    res = detect_file(FIXTURES_DIR / "sample.mp4")
    assert res.detected_category == FileCategory.VIDEO
    assert res.mime_type == "video/mp4"
    assert res.confidence == 1.0


def test_detect_legitimate_mov():
    """Minimal MOV header (ftypqt) detects as FileCategory.VIDEO."""
    res = detect_file(FIXTURES_DIR / "sample.mov")
    assert res.detected_category == FileCategory.VIDEO
    assert res.mime_type == "video/quicktime"
    assert res.confidence == 1.0


def test_detect_legitimate_avi():
    """Minimal AVI header (RIFF....AVI) detects as FileCategory.VIDEO."""
    res = detect_file(FIXTURES_DIR / "sample.avi")
    assert res.detected_category == FileCategory.VIDEO
    assert res.mime_type == "video/x-msvideo"
    assert res.confidence == 1.0


def test_detect_legitimate_mkv():
    """Minimal MKV header (EBML doctype matroska) detects as FileCategory.VIDEO."""
    res = detect_file(FIXTURES_DIR / "sample.mkv")
    assert res.detected_category == FileCategory.VIDEO
    assert res.mime_type == "video/x-matroska"
    assert res.confidence == 1.0


def test_detect_legitimate_webm():
    """Minimal WEBM header (EBML doctype webm) detects as FileCategory.VIDEO."""
    res = detect_file(FIXTURES_DIR / "sample.webm")
    assert res.detected_category == FileCategory.VIDEO
    assert res.mime_type == "video/webm"
    assert res.confidence == 1.0


def test_detect_video_masquerading_as_csv(tmp_path: Path):
    """MP4 magic bytes with .csv extension correctly identified as VIDEO."""
    fake_csv = tmp_path / "video.csv"
    fake_csv.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")
    res = detect_file(fake_csv)
    assert res.detected_category == FileCategory.VIDEO


def test_registry_routes_video_to_videoprocessor():
    """ProcessorRegistry returns an instance of VideoProcessor for FileCategory.VIDEO."""
    proc = get_processor(FileCategory.VIDEO)
    assert isinstance(proc, VideoProcessor)
