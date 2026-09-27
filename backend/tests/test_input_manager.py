"""Unit and security tests for InputManager in backend/core/input_manager.py."""

from pathlib import Path
import unittest.mock as mock
import pytest

from backend.core.input_manager import InputManager, MAX_EXCEL_CELLS
from backend.core.exceptions import FileValidationError
from backend.config import SESSIONS_DIR

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


def test_validate_and_save_valid_csv(tmp_path: Path):
    """Test saving a standard valid CSV fixture."""
    csv_fixture = FIXTURES_DIR / "sample.csv"
    session_id, saved_path = InputManager.validate_and_save(
        uploaded_file=csv_fixture,
        original_filename="sample.csv",
        sessions_dir=tmp_path,
    )
    assert saved_path.exists()
    assert saved_path.name == "input.csv"
    assert saved_path.parent.name == session_id
    assert saved_path.stat().st_size == csv_fixture.stat().st_size


def test_validate_and_save_valid_xlsx(tmp_path: Path):
    """Test saving a valid Excel workbook fixture."""
    xlsx_fixture = FIXTURES_DIR / "sample.xlsx"
    session_id, saved_path = InputManager.validate_and_save(
        uploaded_file=xlsx_fixture,
        original_filename="sample.xlsx",
        sessions_dir=tmp_path,
    )
    assert saved_path.exists()
    assert saved_path.name == "input.xlsx"
    assert saved_path.parent.name == session_id


def test_validate_and_save_valid_json(tmp_path: Path):
    """Test saving a valid JSON fixture."""
    json_fixture = FIXTURES_DIR / "sample.json"
    session_id, saved_path = InputManager.validate_and_save(
        uploaded_file=json_fixture,
        original_filename="sample.json",
        sessions_dir=tmp_path,
    )
    assert saved_path.exists()
    assert saved_path.name == "input.json"
    assert saved_path.parent.name == session_id


def test_security_path_traversal_prevention(tmp_path: Path):
    """[FIX F3] Security Test: Crafted path traversal in original filename MUST NOT escape session folder."""
    csv_fixture = FIXTURES_DIR / "path_traversal_attempt.csv"
    malicious_filename = "../../../evil.csv"

    session_id, saved_path = InputManager.validate_and_save(
        uploaded_file=csv_fixture,
        original_filename=malicious_filename,
        sessions_dir=tmp_path,
    )

    expected_session_dir = (tmp_path / session_id).resolve()
    resolved_saved_path = saved_path.resolve()

    # REAL ASSERTIONS:
    # 1. Path MUST be strictly inside the assigned session directory
    assert expected_session_dir in resolved_saved_path.parents, (
        f"Path traversal escape! {resolved_saved_path} is not inside {expected_session_dir}"
    )

    # 2. Stored filename MUST be the fixed internal name, NOT the attacker's filename
    assert resolved_saved_path.name == "input.csv"
    assert "evil.csv" not in str(resolved_saved_path)

    # 3. Ensure no evil.csv was created anywhere in parent directories
    for parent in expected_session_dir.parents:
        assert not (parent / "evil.csv").exists()


def test_security_excel_decompression_guard(tmp_path: Path):
    """[FIX F4] Security Test: Guard trips on Excel files exceeding decompressed cell count limit."""
    xlsx_fixture = FIXTURES_DIR / "sample.xlsx"

    # Simulate an Excel sheet reporting 1,000,000 rows by 10 columns (10,000,000 cells > 5,000,000 limit)
    mock_ws = mock.MagicMock()
    mock_ws.max_row = 1_000_000
    mock_ws.max_column = 10

    mock_wb = mock.MagicMock()
    mock_wb.sheetnames = ["BigSheet"]
    mock_wb.__getitem__.return_value = mock_ws

    with mock.patch("openpyxl.load_workbook", return_value=mock_wb):
        with pytest.raises(FileValidationError) as exc_info:
            InputManager.validate_and_save(
                uploaded_file=xlsx_fixture,
                original_filename="bomb.xlsx",
                sessions_dir=tmp_path,
            )

        err_msg = str(exc_info.value)
        assert "exceeds maximum cell limit" in err_msg
        assert "Potential decompression bomb" in err_msg


def test_rejection_unsupported_extension(tmp_path: Path):
    """Verify rejection of non-allowlisted file extensions (.xml)."""
    with pytest.raises(FileValidationError) as exc_info:
        InputManager.validate_and_save(
            uploaded_file=b"fake data",
            original_filename="oversized_placeholder.xml",
            sessions_dir=tmp_path,
        )
    assert "Unsupported file format '.xml'" in str(exc_info.value)


def test_rejection_empty_file(tmp_path: Path):
    """Verify rejection of 0-byte uploads."""
    with pytest.raises(FileValidationError) as exc_info:
        InputManager.validate_and_save(
            uploaded_file=b"",
            original_filename="empty.csv",
            sessions_dir=tmp_path,
        )
    assert "The uploaded file is empty (0 bytes)" in str(exc_info.value)


