"""Unit and parity tests for DataUnderstanding (Stage 1) in backend/core/understanding.py."""

import json
from pathlib import Path
import pytest

from backend.core.understanding import DataUnderstanding
from backend.core.exceptions import FileValidationError
from backend.models.schemas import InferredType

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


@pytest.fixture(scope="module")
def expected_profile():
    """Load canonical ground truth expected profile."""
    profile_path = FIXTURES_DIR / "expected_sample_profile.json"
    with open(profile_path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_profile_sample_csv(expected_profile):
    """Verify profile_data on sample.csv matches expected ground truth field by field."""
    csv_path = FIXTURES_DIR / "sample.csv"
    profile = DataUnderstanding.profile_data(csv_path)

    # 1. Global properties
    exp_props = expected_profile["file_properties"]
    assert profile.file_format == "csv"
    assert profile.encoding in ("utf-8", "ascii")
    assert profile.row_count == exp_props["row_count"] == 50
    assert profile.column_count == exp_props["column_count"] == 6
    assert profile.duplicate_row_count == exp_props["duplicate_row_count"] == 4
    assert profile.duplicate_percentage == exp_props["duplicate_percentage"] == 8.0

    # 2. Columns match
    assert [c.name for c in profile.columns] == exp_props["columns"]

    # 3. Column profiles match
    exp_cols = expected_profile["column_profiles"]
    col_map = {c.name: c for c in profile.columns}

    for col_name, exp_data in exp_cols.items():
        act_col = col_map[col_name]
        assert act_col.inferred_type.value == exp_data["inferred_type"], (
            f"Type mismatch on {col_name}: expected {exp_data['inferred_type']}, got {act_col.inferred_type.value}"
        )
        assert act_col.null_count == exp_data["null_count"]
        assert act_col.null_percentage == exp_data["null_percentage"]
        assert act_col.unique_count == exp_data["unique_count"]

    # 4. Check Date quality issue for mixed formats
    date_col = col_map["Date"]
    assert any("Mixed date formats" in issue for issue in date_col.quality_issues)


def test_profile_sample_xlsx(expected_profile):
    """Verify profile_data on sample.xlsx matches expected ground truth."""
    xlsx_path = FIXTURES_DIR / "sample.xlsx"
    profile = DataUnderstanding.profile_data(xlsx_path)

    exp_props = expected_profile["file_properties"]
    assert profile.file_format == "xlsx"
    assert profile.row_count == exp_props["row_count"] == 50
    assert profile.column_count == exp_props["column_count"] == 6
    assert profile.duplicate_row_count == exp_props["duplicate_row_count"] == 4
    assert profile.duplicate_percentage == exp_props["duplicate_percentage"] == 8.0
    assert len(profile.sheet_names) >= 1

    exp_cols = expected_profile["column_profiles"]
    col_map = {c.name: c for c in profile.columns}
    for col_name, exp_data in exp_cols.items():
        act_col = col_map[col_name]
        assert act_col.inferred_type.value == exp_data["inferred_type"]
        assert act_col.null_count == exp_data["null_count"]
        assert act_col.null_percentage == exp_data["null_percentage"]
        assert act_col.unique_count == exp_data["unique_count"]


def test_profile_sample_json(expected_profile):
    """Verify profile_data on sample.json matches expected ground truth."""
    json_path = FIXTURES_DIR / "sample.json"
    profile = DataUnderstanding.profile_data(json_path)

    exp_props = expected_profile["file_properties"]
    assert profile.file_format == "json"
    assert profile.row_count == exp_props["row_count"] == 50
    assert profile.column_count == exp_props["column_count"] == 6
    assert profile.duplicate_row_count == exp_props["duplicate_row_count"] == 4
    assert profile.duplicate_percentage == exp_props["duplicate_percentage"] == 8.0

    exp_cols = expected_profile["column_profiles"]
    col_map = {c.name: c for c in profile.columns}
    for col_name, exp_data in exp_cols.items():
        act_col = col_map[col_name]
        assert act_col.inferred_type.value == exp_data["inferred_type"]
        assert act_col.null_count == exp_data["null_count"]
        assert act_col.null_percentage == exp_data["null_percentage"]
        assert act_col.unique_count == exp_data["unique_count"]


def test_three_format_profile_parity():
    """Verify exact parity of profile_data across CSV, XLSX, and JSON."""
    csv_profile = DataUnderstanding.profile_data(FIXTURES_DIR / "sample.csv")
    xlsx_profile = DataUnderstanding.profile_data(FIXTURES_DIR / "sample.xlsx")
    json_profile = DataUnderstanding.profile_data(FIXTURES_DIR / "sample.json")

    assert csv_profile.row_count == xlsx_profile.row_count == json_profile.row_count == 50
    assert csv_profile.column_count == xlsx_profile.column_count == json_profile.column_count == 6
    assert (
        csv_profile.duplicate_row_count
        == xlsx_profile.duplicate_row_count
        == json_profile.duplicate_row_count
        == 4
    )

    csv_types = [c.inferred_type for c in csv_profile.columns]
    xlsx_types = [c.inferred_type for c in xlsx_profile.columns]
    json_types = [c.inferred_type for c in json_profile.columns]
    assert csv_types == xlsx_types == json_types

    csv_nulls = [c.null_count for c in csv_profile.columns]
    xlsx_nulls = [c.null_count for c in xlsx_profile.columns]
    json_nulls = [c.null_count for c in json_profile.columns]
    assert csv_nulls == xlsx_nulls == json_nulls == [0, 0, 6, 0, 0, 0]


def test_malformed_csv_rejection():
    """Verify that structurally malformed CSV raises FileValidationError with plain message."""
    malformed_path = FIXTURES_DIR / "malformed.csv"
    with pytest.raises(FileValidationError) as exc_info:
        DataUnderstanding.profile_data(malformed_path)
    err = str(exc_info.value)
    assert "Failed to parse CSV file" in err
    assert not err.startswith("Traceback")


def test_nonexistent_file_rejection(tmp_path: Path):
    """Verify rejection when profiling target does not exist."""
    ghost_file = tmp_path / "ghost.csv"
    with pytest.raises(FileValidationError) as exc_info:
        DataUnderstanding.profile_data(ghost_file)
    assert "File not found" in str(exc_info.value)
