"""Unit and integration tests for ArchiveProcessor."""

from pathlib import Path
import shutil
import zipfile
import pytest
from PIL import Image

from backend.core.archive_security import safe_extract_archive
from backend.models.schemas import Objective, ObjectiveCategory, Plan, Step
from backend.processors.archive import ArchiveProcessor

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "archives"
SAMPLE_ZIP = FIXTURES_DIR / "sample.zip"
SAMPLE_TAR = FIXTURES_DIR / "sample.tar"
SAMPLE_GZ = FIXTURES_DIR / "sample.gz"


@pytest.fixture
def processor() -> ArchiveProcessor:
    return ArchiveProcessor()


class TestArchiveProcessor:
    """Test suite for ArchiveProcessor profiling, execution, and validation."""

    def test_profile_sample_zip_detects_cross_category_content(self, processor: ArchiveProcessor):
        """Profile should detect tabular (csv), image (jpg), and document (txt) via magic bytes."""
        prof = processor.profile(SAMPLE_ZIP, session_id="test_prof_1")

        assert prof["file_format"] == "zip"
        assert prof["entry_count"] == 3
        assert prof["total_uncompressed_bytes"] > 0

        # Contained categories must reflect the 3 different types
        cats = set(prof["contained_categories"])
        assert "tabular" in cats
        assert "image" in cats
        assert "document" in cats

        # Detailed entry inspection
        filenames = {e["filename"] for e in prof["entries"]}
        assert filenames == {"data.csv", "image.jpg", "notes.txt"}

    def test_profile_sample_tar(self, processor: ArchiveProcessor):
        """Profile should handle TAR archives."""
        prof = processor.profile(SAMPLE_TAR, session_id="test_prof_tar")

        assert prof["file_format"] == "tar"
        assert prof["entry_count"] == 2
        cats = set(prof["contained_categories"])
        assert "tabular" in cats
        assert "document" in cats

    def test_profile_sample_gz(self, processor: ArchiveProcessor):
        """Profile should handle standalone GZ files."""
        prof = processor.profile(SAMPLE_GZ, session_id="test_prof_gz")

        assert prof["file_format"] == "gz"
        assert prof["entry_count"] == 1
        assert prof["total_uncompressed_bytes"] > 0

    def test_execute_list_contents(self, processor: ArchiveProcessor, tmp_path: Path):
        """execute with list_contents produces a validated output archive and listing."""
        plan = Plan(
            plan_id="plan_list",
            session_id="session_list",
            objectives=[
                Objective(category=ObjectiveCategory.REPORT, description="list contents of archive")
            ],
            steps=[
                Step(
                    step_number=1,
                    tool_name="list_contents",
                    description="List archive members",
                    parameters={},
                    expected_output="Archive listed.",
                )
            ],
            rationale="List files in archive",
        )

        state = processor.execute(SAMPLE_ZIP, plan, output_dir=tmp_path)
        assert state["total_files"] == 3
        assert state["result_archive_path"].exists()

        # Validate output
        val = processor.validate_output(SAMPLE_ZIP, state, plan)
        assert val.is_valid is True
        assert "SECURITY_VERIFIED" in val.checks_passed
        assert "ENTRY_COUNT_MATCHED" in val.checks_passed

    def test_execute_extract_and_process_cross_category(self, processor: ArchiveProcessor, tmp_path: Path):
        """execute with image resize processes inner image and repackages archive."""
        plan = Plan(
            plan_id="plan_proc",
            session_id="session_proc",
            objectives=[
                Objective(category=ObjectiveCategory.TRANSFORM, description="resize images to 50x50")
            ],
            steps=[
                Step(
                    step_number=1,
                    tool_name="resize",
                    description="Resize image to 50x50",
                    parameters={"width": 50, "height": 50},
                    expected_output="Image resized.",
                )
            ],
            rationale="Resize inner images",
        )

        state = processor.execute(SAMPLE_ZIP, plan, output_dir=tmp_path)
        assert state["total_files"] == 3
        assert state["processed_count"] >= 1  # image.jpg was processed

        out_zip = state["result_archive_path"]
        assert out_zip.exists()

        # Validate
        val = processor.validate_output(SAMPLE_ZIP, state, plan)
        assert val.is_valid is True

        # Reopen and verify contents of repackaged archive
        inspect_dir = tmp_path / "inspect"
        extracted = safe_extract_archive(out_zip, inspect_dir)
        extracted_names = {f.name for f in extracted}
        assert "image.jpg" in extracted_names
        assert "data.csv" in extracted_names
        assert "notes.txt" in extracted_names

        # Check that image.jpg was actually resized to 50x50!
        img_file = next(f for f in extracted if f.name == "image.jpg")
        with Image.open(img_file) as im:
            assert im.size == (50, 50)

    def test_validate_output_detects_corrupted_or_missing(self, processor: ArchiveProcessor, tmp_path: Path):
        """validate_output fails gracefully when output file is missing or invalid."""
        plan = Plan(
            plan_id="p", session_id="s", objectives=[], steps=[], rationale=""
        )

        # Missing file
        missing_state = {"result_archive_path": tmp_path / "nonexistent.zip", "total_files": 1}
        val_missing = processor.validate_output(SAMPLE_ZIP, missing_state, plan)
        assert val_missing.is_valid is False
        assert "EMPTY_OUTPUT_ARCHIVE" in val_missing.checks_failed

        # Entry count mismatch
        empty_zip = tmp_path / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            pass
        mismatch_state = {"result_archive_path": empty_zip, "total_files": 3}
        val_mismatch = processor.validate_output(SAMPLE_ZIP, mismatch_state, plan)
        assert val_mismatch.is_valid is False
        assert "ENTRY_COUNT_MISMATCH" in val_mismatch.checks_failed

    def test_export_archive(self, processor: ArchiveProcessor, tmp_path: Path):
        """Export archive to requested target directory and stem."""
        state = {"result_archive_path": SAMPLE_ZIP}
        out_dir = tmp_path / "exports"
        exported = processor.export(state, output_format="zip", output_dir=out_dir, filename_stem="final_archive")

        assert exported.exists()
        assert exported.name == "final_archive.zip"
        assert exported.stat().st_size == SAMPLE_ZIP.stat().st_size
