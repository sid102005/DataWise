"""Security and resilience tests for DataWise archive handling.

Verifies Zip-Slip path-traversal prevention, archive-bomb resource exhaustion
protection, symlink rejection, and cleanup safety under adversarial conditions.
"""

import io
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile
import pytest

from backend.core.archive_security import (
    MAX_ARCHIVE_ENTRY_COUNT,
    MAX_DECLARED_UNCOMPRESSED_SIZE_BYTES,
    SafeArchiveWorkspace,
    safe_extract_archive,
    validate_archive_security,
)
from backend.core.exceptions import ArchiveSecurityError

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "archives"
SAMPLE_ZIP = FIXTURES_DIR / "sample.zip"
ZIP_SLIP = FIXTURES_DIR / "zip_slip.zip"
ARCHIVE_BOMB = FIXTURES_DIR / "archive_bomb.zip"
SAMPLE_TAR = FIXTURES_DIR / "sample.tar"
SAMPLE_GZ = FIXTURES_DIR / "sample.gz"


class TestArchiveSecurityGuards:
    """Rigorous pre-extraction security tests."""

    def test_zip_slip_rejected_before_extraction(self, tmp_path: Path):
        """Confirm malicious zip with path-traversal entry is refused without extracting."""
        target_dir = tmp_path / "extracted"

        with pytest.raises(ArchiveSecurityError) as exc_info:
            validate_archive_security(ZIP_SLIP)
        assert "Path traversal entry detected" in str(exc_info.value)
        assert "../../evil.txt" in str(exc_info.value)

        # Confirm safe_extract_archive also refuses and creates no breakout files
        with pytest.raises(ArchiveSecurityError):
            safe_extract_archive(ZIP_SLIP, target_dir)

        # Confirm evil.txt was never written anywhere
        assert not (tmp_path / "evil.txt").exists()
        assert not (target_dir / "evil.txt").exists()

    def test_archive_bomb_declared_size_rejected_before_extraction(self, tmp_path: Path):
        """Confirm archive with declared uncompressed size > 500 MB is rejected immediately."""
        target_dir = tmp_path / "extracted"

        with pytest.raises(ArchiveSecurityError) as exc_info:
            validate_archive_security(ARCHIVE_BOMB)
        assert "Declared uncompressed size" in str(exc_info.value)
        assert "decompression bomb" in str(exc_info.value).lower()

        # Confirm extraction is never attempted
        with pytest.raises(ArchiveSecurityError):
            safe_extract_archive(ARCHIVE_BOMB, target_dir)

        assert not target_dir.exists() or len(list(target_dir.iterdir())) == 0

    def test_entry_count_bomb_rejected(self, tmp_path: Path):
        """Confirm archive with excessive member count (>10,000) is rejected."""
        bomb_zip = tmp_path / "many_files.zip"
        with zipfile.ZipFile(bomb_zip, "w") as zf:
            for i in range(MAX_ARCHIVE_ENTRY_COUNT + 5):
                zf.writestr(f"file_{i}.txt", b"x")

        with pytest.raises(ArchiveSecurityError) as exc_info:
            validate_archive_security(bomb_zip)
        assert "Entry count" in str(exc_info.value)
        assert "exceeds maximum allowed" in str(exc_info.value)

    def test_tar_path_traversal_rejected(self, tmp_path: Path):
        """Confirm TAR archive with traversal entry is refused."""
        bad_tar = tmp_path / "bad.tar"
        with tarfile.open(bad_tar, "w") as tf:
            info = tarfile.TarInfo(name="../escaped.txt")
            info.size = 4
            tf.addfile(info, io.BytesIO(b"data"))

        with pytest.raises(ArchiveSecurityError) as exc_info:
            validate_archive_security(bad_tar)
        assert "Path traversal entry detected" in str(exc_info.value)

    def test_symlink_in_archive_rejected(self, tmp_path: Path):
        """Confirm symbolic links in archives are strictly forbidden."""
        sym_tar = tmp_path / "symlink.tar"
        with tarfile.open(sym_tar, "w") as tf:
            info = tarfile.TarInfo(name="link_to_root")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tf.addfile(info)

        with pytest.raises(ArchiveSecurityError) as exc_info:
            validate_archive_security(sym_tar)
        assert "Link detected in entry" in str(exc_info.value)

    def test_absolute_path_in_zip_rejected(self, tmp_path: Path):
        """Confirm absolute paths like /etc/shadow or C:\\Windows in archives are rejected."""
        abs_zip = tmp_path / "abs.zip"
        with zipfile.ZipFile(abs_zip, "w") as zf:
            zf.writestr("/root/secret.txt", b"data")

        with pytest.raises(ArchiveSecurityError) as exc_info:
            validate_archive_security(abs_zip)
        assert "Path traversal entry detected" in str(exc_info.value)


class TestSafeArchiveExtraction:
    """Tests for legitimate archives and temporary workspace lifecycle."""

    def test_legitimate_zip_extracts_successfully(self, tmp_path: Path):
        """Legitimate zip extracts cleanly and produces expected files."""
        target_dir = tmp_path / "out_zip"
        files = safe_extract_archive(SAMPLE_ZIP, target_dir)

        assert len(files) == 3
        names = {f.name for f in files}
        assert names == {"data.csv", "image.jpg", "notes.txt"}

        # Verify file contents intact
        csv_file = next(f for f in files if f.name == "data.csv")
        assert "Widget" in csv_file.read_text(encoding="utf-8")

    def test_legitimate_tar_extracts_successfully(self, tmp_path: Path):
        """Legitimate tar extracts cleanly."""
        target_dir = tmp_path / "out_tar"
        files = safe_extract_archive(SAMPLE_TAR, target_dir)

        assert len(files) == 2
        names = {f.name for f in files}
        assert names == {"data.csv", "notes.txt"}

    def test_legitimate_gz_extracts_successfully(self, tmp_path: Path):
        """Legitimate gz extracts cleanly."""
        target_dir = tmp_path / "out_gz"
        files = safe_extract_archive(SAMPLE_GZ, target_dir)

        assert len(files) == 1
        assert "Widget" in files[0].read_text(encoding="utf-8")

    def test_failure_cleanup_path_guaranteed(self, tmp_path: Path, monkeypatch):
        """Ensure that if an error occurs during extraction, all temp artifacts are removed."""
        target_dir = tmp_path / "fail_cleanup"

        # Monkeypatch shutil.copyfileobj to raise an IOError mid-extraction
        def mock_copyfileobj(fsrc, fdst, length=None):
            raise IOError("Simulated disk error during extraction")

        monkeypatch.setattr(shutil, "copyfileobj", mock_copyfileobj)

        with pytest.raises(IOError):
            safe_extract_archive(SAMPLE_ZIP, target_dir)

        # Guarantee target_dir was cleaned up
        assert not target_dir.exists()

    def test_safe_archive_workspace_lifecycle(self, tmp_path: Path):
        """Context manager provides an isolated directory and cleans up on exit."""
        session_dir = tmp_path / "session_123"
        session_dir.mkdir()

        created_dir: Path | None = None
        with SafeArchiveWorkspace(session_dir) as ws:
            created_dir = ws
            assert created_dir.exists()
            assert created_dir.parent == session_dir
            # Create a file inside workspace
            (created_dir / "temp.dat").write_text("hello")
            assert (created_dir / "temp.dat").exists()

        # After exiting context, workspace must be completely deleted
        assert not created_dir.exists()
