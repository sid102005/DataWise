"""DataWise Data Understanding (Stage 1).

Responsible for:
- Format and character encoding detection
- Tabular parsing across CSV, Excel (.xlsx), and JSON
- Semantic column type inference (numeric, date, categorical, id, text)
- Data quality profiling (null counts, duplicate rows, quality flags)
- Producing validated, metadata-only DataProfile objects
"""

import json
from pathlib import Path
import re
from typing import Literal
from dateutil.parser import parse as parse_date
import openpyxl
import pandas as pd

from backend.core.exceptions import FileValidationError
from backend.models.schemas import ColumnInfo, DataProfile, InferredType


class DataUnderstanding:
    """Stage 1 Engine: Profiles structure and quality of tabular files."""

    @staticmethod
    def detect_format_and_encoding(file_path: Path) -> tuple[str, str]:
        """Detect file format extension and text encoding.

        Args:
            file_path: Path to the target file.

        Returns:
            Tuple of (format_extension, encoding_string).

        Raises:
            FileValidationError: If format is unsupported or file unreadable.
        """
        if not file_path.exists():
            raise FileValidationError(f"File not found for profiling: {file_path}")

        ext = file_path.suffix.lstrip(".").lower()
        if ext not in {"csv", "xlsx", "json"}:
            raise FileValidationError(
                f"Unsupported format '{ext}'. Only CSV, Excel (.xlsx), and JSON are supported."
            )

        encoding = "utf-8"
        if ext == "csv":
            # Test UTF-8 decoding on initial chunk; fallback to latin-1 if invalid
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    f.read(65536)
                encoding = "utf-8"
            except UnicodeDecodeError:
                encoding = "latin-1"

        return ext, encoding

    @staticmethod
    def parse_dataframe(
        file_path: Path,
        format_type: str | None = None,
        encoding: str = "utf-8",
    ) -> tuple[pd.DataFrame, list[str]]:
        """Parse raw file into a pandas DataFrame and extract workbook sheet names.

        Args:
            file_path: File location.
            format_type: Explicit format override ('csv', 'xlsx', 'json').
            encoding: Text character encoding (for CSV).

        Returns:
            Tuple of (DataFrame, sheet_names_list).

        Raises:
            FileValidationError: If parsing fails or data is structurally invalid.
        """
        fmt = format_type or file_path.suffix.lstrip(".").lower()
        sheet_names: list[str] = []

        try:
            if fmt == "csv":
                df = pd.read_csv(file_path, encoding=encoding)
            elif fmt == "xlsx":
                # Extract sheet names
                wb = openpyxl.load_workbook(file_path, read_only=True)
                sheet_names = list(wb.sheetnames)
                wb.close()
                df = pd.read_excel(file_path, sheet_name=0, engine="openpyxl")
            elif fmt == "json":
                df = pd.read_json(file_path)
            else:
                raise FileValidationError(f"Unsupported parsing format: {fmt}")
        except FileValidationError:
            raise
        except Exception as e:
            raise FileValidationError(
                f"Failed to parse {fmt.upper()} file: {str(e)}",
                details=str(e),
            )

        if df.empty or len(df.columns) == 0:
            raise FileValidationError("Uploaded dataset is empty or contains no columns.")

        return df, sheet_names

    @classmethod
    def infer_column_types(cls, df: pd.DataFrame) -> list[ColumnInfo]:
        """Infer semantic types and build individual ColumnInfo records.

        Categorization Rules:
        - ID: Column name contains/ends with 'id' AND high uniqueness ratio (>= 80%).
        - DATE: datetime64 dtypes, column name matching 'date/time/timestamp', or parses as dates.
        - NUMERIC: Standard integer or float dtypes.
        - CATEGORICAL: Low-cardinality discrete sets (<= 20 unique values or < 20% of rows).
        - TEXT: Freeform strings, high-cardinality descriptive text.

        Args:
            df: Target DataFrame.

        Returns:
            List of ColumnInfo objects for each column.
        """
        columns: list[ColumnInfo] = []
        total_rows = len(df)

        for col_name in df.columns:
            series = df[col_name]
            col_str = str(col_name)
            col_lower = col_str.lower()
            null_count = int(series.isna().sum())
            null_pct = round((null_count / total_rows) * 100, 2) if total_rows > 0 else 0.0
            unique_count = int(series.nunique(dropna=True))
            non_null = series.dropna()
            quality_issues: list[str] = []

            if null_count > 0:
                quality_issues.append(f"{null_count} missing values ({null_pct:.1f}%)")

            inferred: InferredType

            # 1. Identifier inference
            is_id_name = bool(re.search(r"(^|[_\s])id($|[_\s])", col_lower))
            if is_id_name and (unique_count / max(1, len(non_null))) >= 0.8:
                inferred = InferredType.ID

            # 2. Date inference
            elif pd.api.types.is_datetime64_any_dtype(series):
                inferred = InferredType.DATE
            elif (
                bool(re.search(r"(date|time|timestamp)", col_lower))
                or (pd.api.types.is_string_dtype(series) and len(non_null) > 0)
            ):
                sample_vals = non_null.head(10).astype(str)
                date_matches = 0
                for val in sample_vals:
                    try:
                        parse_date(val)
                        date_matches += 1
                    except Exception:
                        pass
                if len(sample_vals) > 0 and date_matches >= len(sample_vals) * 0.8:
                    inferred = InferredType.DATE
                elif pd.api.types.is_numeric_dtype(series):
                    inferred = InferredType.NUMERIC
                elif unique_count <= 20 or (total_rows > 0 and unique_count / total_rows < 0.2):
                    inferred = InferredType.CATEGORICAL
                else:
                    inferred = InferredType.TEXT
            # 3. Numeric inference
            elif pd.api.types.is_numeric_dtype(series):
                inferred = InferredType.NUMERIC

            # 4. Categorical inference
            elif unique_count <= 20 or (total_rows > 0 and unique_count / total_rows < 0.2):
                inferred = InferredType.CATEGORICAL

            # 5. Text fallback
            else:
                inferred = InferredType.TEXT

            # Quality check for Date: check for mixed date formats
            if inferred == InferredType.DATE and pd.api.types.is_string_dtype(series):
                str_dates = non_null.astype(str)
                iso_matches = int(str_dates.str.match(r"^\d{4}-\d{2}-\d{2}").sum())
                slash_matches = int(str_dates.str.match(r"^\d{1,2}/\d{1,2}/\d{4}").sum())
                if iso_matches > 0 and slash_matches > 0:
                    quality_issues.append(
                        f"Mixed date formats detected: {iso_matches} ISO (YYYY-MM-DD), {slash_matches} slash (DD/MM/YYYY)"
                    )

            col_info = ColumnInfo(
                name=col_str,
                inferred_type=inferred,
                raw_dtype=str(series.dtype),
                null_count=null_count,
                null_percentage=null_pct,
                unique_count=unique_count,
                quality_issues=quality_issues,
            )
            columns.append(col_info)

        return columns

    @classmethod
    def calculate_quality_metrics(
        cls,
        df: pd.DataFrame,
        columns: list[ColumnInfo],
    ) -> tuple[int, float, list[str]]:
        """Compute dataset-level duplicate counts and synthesize quality flags."""
        total_rows = len(df)
        dup_count = int(df.duplicated().sum())
        dup_pct = round((dup_count / total_rows) * 100, 2) if total_rows > 0 else 0.0

        flags: list[str] = []
        if dup_count > 0:
            flags.append(f"{dup_count} duplicate rows detected ({dup_pct:.1f}% of total).")

        for col in columns:
            if col.null_count > 0:
                flags.append(
                    f"Column '{col.name}' has {col.null_count} missing values ({col.null_percentage:.1f}%)."
                )
            for issue in col.quality_issues:
                issue_str = f"Column '{col.name}': {issue}"
                if issue_str not in flags:
                    flags.append(issue_str)

        return dup_count, dup_pct, flags

    @classmethod
    def profile_data(cls, file_path: Path, session_id: str | None = None) -> DataProfile:
        """End-to-end Stage 1 profiling execution.

        Args:
            file_path: Absolute or relative path to tabular data file.
            session_id: Optional tracking identifier.

        Returns:
            Validated, populated DataProfile object.
        """
        ext, encoding = cls.detect_format_and_encoding(file_path)
        df, sheet_names = cls.parse_dataframe(file_path, format_type=ext, encoding=encoding)
        columns = cls.infer_column_types(df)
        dup_count, dup_pct, quality_flags = cls.calculate_quality_metrics(df, columns)

        format_literal: Literal["csv", "xlsx", "json"]
        if ext in ("csv", "xlsx", "json"):
            format_literal = ext  # type: ignore
        else:
            raise FileValidationError(f"Invalid format {ext}")

        return DataProfile(
            file_format=format_literal,
            encoding=encoding,
            row_count=len(df),
            column_count=len(df.columns),
            duplicate_row_count=dup_count,
            duplicate_percentage=dup_pct,
            columns=columns,
            sheet_names=sheet_names,
            quality_flags=quality_flags,
        )
