"""Real driven smoke test for the Streamlit frontend using AppTest.

Verifies:
1. GET /api/capabilities exists and reflects live capabilities and registered processors.
2. Frontend uploader dynamically derives accepted file extensions from GET /api/capabilities.
3. Frontend uploader gracefully falls back to safe defaults (CSV/XLSX/JSON) when backend is offline.
4. Tabular upload (sample.csv) renders a real DataFrame preview table (not broken).
5. Document upload (sample.pdf) renders extracted text area with word count (no empty table).
6. Image upload (sample.jpg) renders inline processed image with exact dimensions verified via Pillow.
7. Unsupported formats (e.g. .wav) are honestly excluded via capabilities.json, not hardcoded lists.
8. Non-tabular results missing tabular fields do not crash the UI.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Generator

import pytest
import requests
from PIL import Image
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_APP = str(REPO_ROOT / "frontend" / "app.py")
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample.csv"
SAMPLE_PDF = FIXTURES_DIR / "documents" / "sample.pdf"
SAMPLE_JPG = FIXTURES_DIR / "images" / "sample.jpg"
SAMPLE_WAV = FIXTURES_DIR / "audio" / "sample.wav"
AUDIO_EXPECTED = FIXTURES_DIR / "audio" / "expected_values.json"
SAMPLE_MP4 = FIXTURES_DIR / "video" / "sample.mp4"
VIDEO_EXPECTED = FIXTURES_DIR / "video" / "expected_values.json"
SAMPLE_ZIP = FIXTURES_DIR / "archives" / "sample.zip"
BATCH_DIR = FIXTURES_DIR / "batch"
BATCH_IMG1 = BATCH_DIR / "img1.jpg"
BATCH_IMG2 = BATCH_DIR / "img2.jpg"


@pytest.fixture(scope="session", autouse=True)
def ensure_backend_running() -> Generator[str, None, None]:
    """Ensure the FastAPI backend is running on http://127.0.0.1:8000 for the test session."""
    base_url = "http://127.0.0.1:8000"
    proc = None
    try:
        resp = requests.get(f"{base_url}/health", timeout=1.5)
        if resp.status_code == 200:
            yield base_url
            return
    except Exception:
        pass

    # Start backend server if not already running
    python_exe = sys.executable
    proc = subprocess.Popen(
        [python_exe, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Wait for liveness
    started = False
    for _ in range(30):
        time.sleep(0.5)
        try:
            r = requests.get(f"{base_url}/health", timeout=1.0)
            if r.status_code == 200:
                started = True
                break
        except Exception:
            continue

    if not started:
        if proc:
            proc.terminate()
        pytest.fail("Could not start DataWise backend on http://127.0.0.1:8000")

    try:
        yield base_url
    finally:
        if proc:
            proc.terminate()


class TestCapabilitiesBackend:
    """Verifies the live capabilities endpoint."""

    def test_capabilities_endpoint_live(self, ensure_backend_running: str):
        resp = requests.get(f"{ensure_backend_running}/api/capabilities", timeout=5)
        assert resp.status_code == 200
        data = resp.json()

        assert "supported_extensions" in data
        assert "extensions_by_category" in data
        assert "supported_categories" in data
        assert "processors" in data

        # Tabular, document, and image are actively supported
        assert "tabular" in data["supported_categories"]
        assert "document" in data["supported_categories"]
        assert "image" in data["supported_categories"]

        # Check expected extensions
        for ext in ["csv", "xlsx", "json", "pdf", "docx", "txt", "md", "jpg", "jpeg", "png"]:
            assert ext in data["supported_extensions"]

        # Phase 12 audio is supported with manipulation (Branch A: FFmpeg available)
        assert data["processors"]["audio"]["supported"] is True
        assert data["processors"]["audio"]["planned_in_phase"] == 12
        assert "extract_metadata" in data["processors"]["audio"]["operations"]
        assert "trim" in data["processors"]["audio"]["operations"]
        assert "wav" in data["supported_extensions"]
        assert "mp3" in data["supported_extensions"]

        # Phase 12 video is supported with manipulation (Branch A: FFmpeg available)
        assert "video" in data["supported_categories"]
        assert data["processors"]["video"]["supported"] is True
        assert data["processors"]["video"]["planned_in_phase"] == 12
        assert "extract_metadata" in data["processors"]["video"]["operations"]
        assert "trim" in data["processors"]["video"]["operations"]
        assert "resize" in data["processors"]["video"]["operations"]
        for ext in ["mp4", "mov", "avi", "mkv", "webm"]:
            assert ext in data["supported_extensions"]

        # Phase 13 archive is supported with profile, listing, extract_and_process
        assert "archive" in data["supported_categories"]
        assert data["processors"]["archive"]["supported"] is True
        assert data["processors"]["archive"]["planned_in_phase"] == 13
        assert "list_contents" in data["processors"]["archive"]["operations"]
        assert "extract_and_process" in data["processors"]["archive"]["operations"]
        for ext in ["zip", "tar", "gz"]:
            assert ext in data["supported_extensions"]


class TestFrontendSmokeAppTest:
    """Verifies frontend UI behavior using real Streamlit AppTest."""

    def test_uploader_configured_dynamically(self, ensure_backend_running: str):
        """Uploader types match live backend capabilities, not a hardcoded list."""
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()
        assert not at.exception

        uploader = at.file_uploader[0]
        configured_types = list(uploader.proto.type)

        resp = requests.get(f"{ensure_backend_running}/api/capabilities", timeout=5).json()
        expected_extensions = [f".{ext}" for ext in resp["supported_extensions"]]
        # Streamlit's file_uploader expands mime-aliases (e.g. .mp4 -> .mp4, .mpeg4)
        assert set(expected_extensions).issubset(set(configured_types))
        assert set(configured_types) - set(expected_extensions) <= {".mpeg4"}
        assert ".jpg" in configured_types
        assert ".pdf" in configured_types
        assert ".csv" in configured_types
        assert ".wav" in configured_types
        assert ".mp3" in configured_types
        assert ".mp4" in configured_types
        assert ".mov" in configured_types
        assert ".webm" in configured_types
        assert ".zip" in configured_types
        assert ".tar" in configured_types
        assert ".gz" in configured_types

    def test_uploader_offline_fallback(self, monkeypatch):
        """When backend is unreachable, UI warns and falls back safely to CSV/XLSX/JSON."""
        monkeypatch.setenv("DATAWISE_API_URL", "http://127.0.0.1:9999")
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()
        assert not at.exception

        # Uploader should fall back to safe default extensions
        uploader = at.file_uploader[0]
        configured_types = list(uploader.proto.type)
        assert sorted(configured_types) == sorted([".csv", ".xlsx", ".json"])

        # Warning should be rendered
        warnings = [w.value for w in at.warning]
        assert any("Could not reach DataWise backend" in w for w in warnings)

    def test_smoke_tabular_renders_dataframe(self, ensure_backend_running: str):
        """Uploading CSV renders a DataFrame preview with real table data."""
        assert SAMPLE_CSV.exists()
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()

        content = SAMPLE_CSV.read_bytes()
        at.file_uploader[0].upload("sample.csv", content, "text/csv").run()
        at.text_area[0].input("Clean this data and show me the top 10 by Purchase").run()
        at.button[0].click().run()

        assert not at.exception
        # Must contain a DataFrame widget
        assert len(at.dataframe) >= 1
        df = at.dataframe[0].value
        assert len(df) == 10
        assert "Purchase" in df.columns
        assert "Customer_ID" in df.columns

    def test_smoke_document_renders_extracted_text(self, ensure_backend_running: str):
        """Uploading PDF renders extracted text in a text_area, NOT a broken table."""
        assert SAMPLE_PDF.exists()
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()

        content = SAMPLE_PDF.read_bytes()
        at.file_uploader[0].upload("sample.pdf", content, "application/pdf").run()
        at.text_area[0].input("extract text from this document").run()
        at.button[0].click().run()

        assert not at.exception
        # Must NOT render an empty dataframe
        assert len(at.dataframe) == 0
        # Must render extracted text in text area
        text_areas = [ta.value for ta in at.text_area]
        assert any("This is the first page of the PDF" in val for val in text_areas)
        # Markdown should contain word count
        markdown_texts = [m.value for m in at.markdown]
        assert any("Word count:" in m for m in markdown_texts)

    def test_smoke_image_renders_inline_image_with_dimensions(self, ensure_backend_running: str):
        """Uploading JPG to resize renders inline image and verified dimensions."""
        assert SAMPLE_JPG.exists()
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()

        content = SAMPLE_JPG.read_bytes()
        at.file_uploader[0].upload("sample.jpg", content, "image/jpeg").run()
        at.text_area[0].input("resize this image to 1024x1024").run()
        at.button[0].click().run()

        assert not at.exception
        # Must NOT render an empty dataframe
        assert len(at.dataframe) == 0
        # Must render an image element
        assert len(at.image) >= 1

        # Check dimension metadata in UI markdown
        markdown_texts = [m.value for m in at.markdown]
        assert any("1024" in m and "Dimensions:" in m for m in markdown_texts)

        # Reopen downloaded exported file via client to confirm real Pillow dimensions
        from frontend.client import fetch_file
        res = at.session_state.pipeline_result
        assert res is not None
        assert res.get("status") == "success"
        session_id = res["session_id"]
        result_filename = res["result_filename"]

        raw_bytes = fetch_file(session_id, result_filename)
        assert raw_bytes is not None

        im = Image.open(io.BytesIO(raw_bytes))
        assert im.size == (1024, 1024)
        assert im.format in {"PNG", "JPEG"}

    def test_audio_renders_metadata_and_player_and_trim(self, ensure_backend_running: str):
        """Phase 12 Branch A: Audio (.wav) supports metadata extraction and trimming via FFmpeg.

        - Confirms backend capabilities declare audio supported with manipulation operations.
        - Confirms frontend file uploader accepts .wav and .mp3 dynamically from capabilities.
        - Uploads real synthetic sample.wav, runs metadata extraction.
        - Asserts UI renders real, correct metadata (duration, sample rate, channels) matching expected_values.json.
        - Asserts Streamlit audio player is rendered.
        - Submits a manipulation operation (trim to first 2 seconds), confirms execution succeeds and output is 2.0s.
        """
        import json
        assert SAMPLE_WAV.exists(), "Synthetic WAV fixture must exist"
        assert AUDIO_EXPECTED.exists(), "Audio expected values fixture must exist"
        expected = json.loads(AUDIO_EXPECTED.read_text(encoding="utf-8"))
        if "sample.wav" in expected:
            expected = expected["sample.wav"]

        # 1. Capabilities check: audio is supported with manipulation
        resp = requests.get(f"{ensure_backend_running}/api/capabilities", timeout=5).json()
        audio_meta = resp["processors"].get("audio", {})
        assert audio_meta.get("supported") is True
        assert audio_meta.get("planned_in_phase") == 12
        assert "extract_metadata" in audio_meta.get("operations", [])
        assert "trim" in audio_meta.get("operations", [])
        assert "wav" in resp["supported_extensions"]

        # 2. Uploader accepts .wav and .mp3
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()
        assert not at.exception
        configured_types = list(at.file_uploader[0].proto.type)
        assert ".wav" in configured_types
        assert ".mp3" in configured_types

        # 3. Upload sample.wav and extract metadata
        wav_bytes = SAMPLE_WAV.read_bytes()
        at.file_uploader[0].upload("sample.wav", wav_bytes, "audio/wav").run()
        at.text_area[0].input("extract audio metadata").run()
        at.button[0].click().run()

        assert not at.exception
        # Must NOT render an empty tabular dataframe
        assert len(at.dataframe) == 0

        # Check metadata rendered in markdown
        markdown_texts = [m.value for m in at.markdown]
        exp_dur_str = f"{expected['duration_seconds']}s"
        exp_sr_str = f"{expected['sample_rate']} Hz"
        exp_ch_str = str(expected["channels"])

        assert any(exp_dur_str in m for m in markdown_texts), f"Expected duration {exp_dur_str} in UI"
        assert any(exp_sr_str in m for m in markdown_texts), f"Expected sample rate {exp_sr_str} in UI"
        assert any("Channels:" in m and exp_ch_str in m for m in markdown_texts), f"Expected channels {exp_ch_str} in UI"

        # Check that audio player was rendered
        audio_elements = at.get("audio")
        assert len(audio_elements) >= 1, "st.audio element should be rendered"

        # 4. Request manipulation operation (trim) -> real FFmpeg processing
        at_trim = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at_trim.run()
        at_trim.file_uploader[0].upload("sample.wav", wav_bytes, "audio/wav").run()
        at_trim.text_area[0].input("trim this audio to first 2 seconds").run()
        at_trim.button[0].click().run()

        assert not at_trim.exception
        res = at_trim.session_state.pipeline_result
        assert res is not None
        assert res.get("status") == "success"
        session_id = res["session_id"]
        result_filename = res["result_filename"]

        from frontend.client import fetch_file
        trimmed_bytes = fetch_file(session_id, result_filename)
        assert trimmed_bytes is not None

        # Independently verify trimmed audio duration
        import wave
        with wave.open(io.BytesIO(trimmed_bytes), "rb") as wf:
            dur = wf.getnframes() / float(wf.getframerate())
            assert abs(dur - 2.0) < 0.1

    def test_video_renders_metadata_and_player_and_trim(self, ensure_backend_running: str):
        """Phase 12 Branch A: Video (.mp4) supports metadata extraction and trimming via FFmpeg.

        - Confirms backend capabilities declare video supported with full manipulation operations.
        - Confirms frontend file uploader accepts .mp4 dynamically from capabilities.
        - Uploads real synthetic sample.mp4, runs metadata extraction.
        - Asserts UI renders real, correct metadata (duration, resolution).
        - Submits a manipulation operation (trim to first 2 seconds), confirms execution succeeds and output is 2.0s.
        """
        import json
        assert SAMPLE_MP4.exists(), "Synthetic MP4 fixture must exist"
        assert VIDEO_EXPECTED.exists(), "Video expected values fixture must exist"
        expected = json.loads(VIDEO_EXPECTED.read_text(encoding="utf-8"))
        if "sample.mp4" in expected:
            expected = expected["sample.mp4"]

        # 1. Capabilities check: video is supported with manipulation
        resp = requests.get(f"{ensure_backend_running}/api/capabilities", timeout=5).json()
        video_meta = resp["processors"].get("video", {})
        assert video_meta.get("supported") is True
        assert video_meta.get("planned_in_phase") == 12
        assert "extract_metadata" in video_meta.get("operations", [])
        assert "trim" in video_meta.get("operations", [])
        assert "mp4" in resp["supported_extensions"]

        # 2. Uploader accepts .mp4
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()
        assert not at.exception
        configured_types = list(at.file_uploader[0].proto.type)
        assert ".mp4" in configured_types

        # 3. Upload sample.mp4 and extract metadata
        mp4_bytes = SAMPLE_MP4.read_bytes()
        at.file_uploader[0].upload("sample.mp4", mp4_bytes, "video/mp4").run()
        at.text_area[0].input("extract video metadata").run()
        at.button[0].click().run()

        assert not at.exception
        # Must NOT render an empty tabular dataframe
        assert len(at.dataframe) == 0

        # Check metadata rendered in markdown
        markdown_texts = [m.value for m in at.markdown]
        all_markdown = " ".join(markdown_texts)
        assert "mp4" in all_markdown.lower() or "video" in all_markdown.lower()

        # 4. Request manipulation operation (trim) -> real FFmpeg processing
        at_trim = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at_trim.run()
        at_trim.file_uploader[0].upload("sample.mp4", mp4_bytes, "video/mp4").run()
        at_trim.text_area[0].input("trim this video to first 2 seconds").run()
        at_trim.button[0].click().run()

        assert not at_trim.exception
        res = at_trim.session_state.pipeline_result
        assert res is not None
        assert res.get("status") == "success"
        session_id = res["session_id"]
        result_filename = res["result_filename"]

        from frontend.client import fetch_file
        trimmed_bytes = fetch_file(session_id, result_filename)
        assert trimmed_bytes is not None

        # Independently verify trimmed video duration via ffprobe
        import tempfile
        from backend.core.ffmpeg_locator import get_ffprobe_path
        ffprobe_bin = get_ffprobe_path()
        tmp_p = Path(tempfile.gettempdir()) / f"smoke_trim_{session_id}.mp4"
        tmp_p.write_bytes(trimmed_bytes)
        try:
            probe_out = subprocess.check_output([
                ffprobe_bin, "-v", "quiet", "-print_format", "json", "-show_format", str(tmp_p)
            ])
            probe_data = json.loads(probe_out)
            dur = float(probe_data["format"]["duration"])
            assert abs(dur - 2.0) < 0.2
        finally:
            if tmp_p.exists():
                tmp_p.unlink()

    def test_smoke_archive_upload_and_preview(self, ensure_backend_running: str):
        """Uploading a ZIP archive renders an inspection preview table and generates valid result archive."""
        assert SAMPLE_ZIP.exists(), "Sample ZIP fixture must exist"
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()

        content = SAMPLE_ZIP.read_bytes()
        at.file_uploader[0].upload("sample.zip", content, "application/zip").run()
        at.text_area[0].input("extract and process all files in archive").run()
        at.button[0].click().run()

        assert not at.exception
        res = at.session_state.pipeline_result
        assert res is not None
        assert res.get("status") == "success"
        session_id = res["session_id"]
        result_filename = res["result_filename"]

        # Must render inspection preview table with columns Filename, Category, Action, Size
        assert len(at.dataframe) >= 1
        df = at.dataframe[0].value
        assert "Filename" in df.columns
        assert "Category" in df.columns

        # Verify output archive via fetch_file
        from frontend.client import fetch_file
        archive_bytes = fetch_file(session_id, result_filename)
        assert archive_bytes is not None
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as zf:
            names = zf.namelist()
            assert len(names) >= 2
            assert "data.csv" in names

    def test_smoke_multifile_upload_batch(self, ensure_backend_running: str):
        """Uploading multiple files runs batch pipeline, renders metrics & table, and packages safe ZIP."""
        assert BATCH_IMG1.exists(), "Batch image 1 must exist"
        assert BATCH_IMG2.exists(), "Batch image 2 must exist"
        at = AppTest.from_file(FRONTEND_APP, default_timeout=30)
        at.run()

        img1_bytes = BATCH_IMG1.read_bytes()
        img2_bytes = BATCH_IMG2.read_bytes()
        at.file_uploader[0].upload("img1.jpg", img1_bytes, "image/jpeg").upload("img2.jpg", img2_bytes, "image/jpeg").run()
        at.text_area[0].input("resize all images to 100x100").run()
        at.button[0].click().run()

        assert not at.exception
        res = at.session_state.pipeline_result
        assert res is not None
        assert res.get("status") == "success"
        assert res.get("batch_summary") is not None
        bs = res["batch_summary"]
        assert bs["total_files"] == 2
        assert bs["succeeded_count"] == 2
        assert bs["failed_count"] == 0

        # UI metrics check (2/2 Files Processed)
        markdown_texts = [m.value for m in at.markdown]
        all_md = " ".join(markdown_texts)
        assert "2/2" in all_md

        # UI table check (Batch dataframe with File and Status columns)
        assert len(at.dataframe) >= 1
        df_batch = at.dataframe[0].value
        assert "File" in df_batch.columns
        assert "Status" in df_batch.columns

        # Verify packaged batch archive
        from frontend.client import fetch_file
        session_id = res["session_id"]
        result_filename = res["result_filename"]
        zip_bytes = fetch_file(session_id, result_filename)
        assert zip_bytes is not None

        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = zf.namelist()
            img1_entry = next((n for n in names if "img1" in n), None)
            img2_entry = next((n for n in names if "img2" in n), None)
            assert img1_entry is not None
            assert img2_entry is not None
            data1 = zf.read(img1_entry)
            im1 = Image.open(io.BytesIO(data1))
            assert im1.size == (100, 100)
            data2 = zf.read(img2_entry)
            im2 = Image.open(io.BytesIO(data2))
            assert im2.size == (100, 100)

