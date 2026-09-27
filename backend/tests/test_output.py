"""Tests for backend/core/output.py.

Verifies:
- export_result_file produces real, openable CSV, XLSX, and JSON files.
- format_table_preview correctly converts NaNs to None, datetimes to ISO strings, and respects row caps.
- synthesize_plain_english_summary reflects actual telemetry numbers from ExecutionResult and ValidationResult.
"""

from __future__ import annotations

import json
from pathlib import Path
import openpyxl
import pandas as pd
import pytest

from backend.core.output import (
    OutputError,
    export_result_file,
    format_table_preview,
    synthesize_plain_english_summary,
)
from backend.models.schemas import (
    ExecutionResult,
    Objective,
    ObjectiveCategory,
    Plan,
    ValidationResult,
)


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Customer_ID": [1001, 1002, 1003],
        "Name": ["Alice", "Bob", "Charlie"],
        "Age": [34, 45, 29],
        "Purchase": [9850.5, 9420.0, 8900.25],
        "Signup_Date": pd.to_datetime(["2024-01-15", "2024-01-18", "2024-01-22"]),
    })


class TestExportResultFile:
    """Verifies that export_result_file produces real, openable files per format."""

    def test_export_csv_produces_readable_file(self, tmp_path: Path, sample_df: pd.DataFrame):
        path = export_result_file(sample_df, tmp_path, "csv", "test_result")
        assert path.exists()
        assert path.suffix == ".csv"
        # Verify it can be read back by pandas
        df_read = pd.read_csv(path)
        assert len(df_read) == 3
        assert list(df_read.columns) == list(sample_df.columns)
        assert df_read["Customer_ID"].tolist() == [1001, 1002, 1003]

    def test_export_xlsx_produces_readable_file(self, tmp_path: Path, sample_df: pd.DataFrame):
        path = export_result_file(sample_df, tmp_path, "xlsx", "test_result")
        assert path.exists()
        assert path.suffix == ".xlsx"
        # Verify openpyxl can inspect the workbook
        wb = openpyxl.load_workbook(path, read_only=True)
        assert "Result" in wb.sheetnames
        wb.close()
        # Verify pandas can read it
        df_read = pd.read_excel(path, engine="openpyxl")
        assert len(df_read) == 3
        assert df_read["Customer_ID"].tolist() == [1001, 1002, 1003]

    def test_export_json_produces_readable_file(self, tmp_path: Path, sample_df: pd.DataFrame):
        path = export_result_file(sample_df, tmp_path, "json", "test_result")
        assert path.exists()
        assert path.suffix == ".json"
        # Verify valid JSON syntax
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["Customer_ID"] == 1001

    def test_export_unsupported_format_raises(self, tmp_path: Path, sample_df: pd.DataFrame):
        with pytest.raises(OutputError, match="Unsupported export format"):
            export_result_file(sample_df, tmp_path, "parquet", "test_result")


class TestFormatTablePreview:
    """Verifies format_table_preview JSON serialization rules."""

    def test_basic_preview(self, sample_df: pd.DataFrame):
        rows, columns = format_table_preview(sample_df, max_rows=10)
        assert len(rows) == 3
        assert columns == ["Customer_ID", "Name", "Age", "Purchase", "Signup_Date"]
        assert rows[0]["Name"] == "Alice"

    def test_nan_converted_to_none(self):
        df = pd.DataFrame({"A": [1.0, float("nan"), 3.0], "B": ["x", None, "z"]})
        rows, _ = format_table_preview(df)
        assert rows[1]["A"] is None
        assert rows[1]["B"] is None

    def test_datetime_converted_to_iso_string(self):
        df = pd.DataFrame({"Date": pd.to_datetime(["2024-01-15 10:30:00"])})
        rows, _ = format_table_preview(df)
        assert isinstance(rows[0]["Date"], str)
        assert "2024-01-15" in rows[0]["Date"]

    def test_max_rows_capped(self):
        df = pd.DataFrame({"x": range(100)})
        rows, _ = format_table_preview(df, max_rows=5)
        assert len(rows) == 5


class TestSynthesizeSummary:
    """Verifies that synthesize_plain_english_summary reflects actual telemetry numbers."""

    def test_summary_contains_actual_row_counts(self):
        plan = Plan(
            plan_id="p1",
            session_id="s1",
            objectives=[Objective(category=ObjectiveCategory.CLEAN, description="clean")],
            steps=[],
        )
        results = [
            ExecutionResult(
                step_number=1,
                tool_name="drop_duplicates",
                success=True,
                rows_before=50,
                rows_after=46,
                columns_before=6,
                columns_after=6,
                summary="Removed 4 duplicate row(s).",
            ),
        ]
        text = synthesize_plain_english_summary(plan, results, None)
        assert "50" in text
        assert "46" in text
        assert "Removed 4 duplicate row(s)." in text

    def test_summary_with_validation_results(self):
        plan = Plan(
            plan_id="p1",
            session_id="s1",
            objectives=[Objective(category=ObjectiveCategory.CLEAN, description="clean")],
            steps=[],
        )
        results = [
            ExecutionResult(
                step_number=1,
                tool_name="drop_duplicates",
                success=True,
                rows_before=50,
                rows_after=46,
                columns_before=6,
                columns_after=6,
                summary="Removed 4 duplicates.",
            ),
        ]
        val = ValidationResult(
            is_valid=True,
            checks_passed=["ROW_COUNT_NONZERO", "ROW_EXPLOSION_GUARD"],
            checks_failed=[],
            details={},
            can_retry=False,
            retry_count=0,
            max_retries=2,
        )
        text = synthesize_plain_english_summary(plan, results, val)
        assert "All 2 validation checks passed." in text

    def test_no_steps_returns_informative_message(self):
        plan = Plan(
            plan_id="p1",
            session_id="s1",
            objectives=[Objective(category=ObjectiveCategory.CLEAN, description="clean")],
            steps=[],
        )
        text = synthesize_plain_english_summary(plan, [], None)
        assert "No steps were executed." in text
