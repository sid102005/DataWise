"""DataWise Stage 6 — Output Generator.

Produces the three user-facing deliverables from the pipeline result:
  1. A downloadable processed file (CSV / XLSX / JSON).
  2. A tabular preview (first N rows as list-of-dicts).
  3. A plain-English "what I did" summary built from actual execution telemetry.

ARCHITECTURE CONTRACT:
- Pure, stateless functions — no LLM calls, no I/O beyond file export.
- synthesize_plain_english_summary() is built exclusively from the structured
  ExecutionResult list; it never uses generic templates or hardcoded phrases.
- chart path discovery is handled by the executor; this module only collects
  them from the PipelineOutput being assembled by pipeline.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from backend.core.exceptions import DataWiseError
from backend.models.schemas import ExecutionResult, Plan, ValidationResult


class OutputError(DataWiseError):
    """Raised when file export or preview generation fails."""


# ---------------------------------------------------------------------------
# Supported export formats
# ---------------------------------------------------------------------------
_EXPORT_FORMATS = {"csv", "xlsx", "json"}


def export_result_file(
    df: pd.DataFrame,
    output_dir: Path,
    fmt: str = "csv",
    filename_stem: str = "result",
) -> Path:
    """Serialize the result DataFrame to disk in the requested format.

    Args:
        df: The processed DataFrame to export.
        output_dir: Directory to write the file into.
        fmt: Target format — 'csv', 'xlsx', or 'json'.
        filename_stem: Base filename without extension (default: 'result').

    Returns:
        Resolved Path to the exported file.

    Raises:
        OutputError: If format is unsupported or serialization fails.
    """
    fmt_clean = fmt.lower().strip()
    if fmt_clean not in _EXPORT_FORMATS:
        raise OutputError(
            f"Unsupported export format '{fmt}'. Supported: {', '.join(sorted(_EXPORT_FORMATS))}."
        )

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    target: Path
    try:
        if fmt_clean == "csv":
            target = output_dir / f"{filename_stem}.csv"
            df.to_csv(target, index=False, encoding="utf-8-sig")

        elif fmt_clean == "xlsx":
            target = output_dir / f"{filename_stem}.xlsx"
            with pd.ExcelWriter(target, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Result")

        elif fmt_clean == "json":
            target = output_dir / f"{filename_stem}.json"
            # Orient 'records' matches the tabular JSON ingestion format used by InputManager
            df.to_json(target, orient="records", indent=2, force_ascii=False)

    except Exception as exc:
        raise OutputError(f"Failed to export result as {fmt_clean}: {exc!s}") from exc

    return target.resolve()


def format_table_preview(
    df: pd.DataFrame,
    max_rows: int = 50,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Generate a JSON-serialisable tabular preview from a DataFrame.

    NaN / NaT values are converted to None for clean JSON output.
    Timestamps are converted to ISO-8601 strings.

    Args:
        df: DataFrame to preview.
        max_rows: Maximum rows to include (default: 50).

    Returns:
        Tuple of:
          - rows: list of dicts, one per row, values are JSON primitives.
          - columns: ordered list of column name strings.
    """
    preview = df.head(max_rows).copy()

    # Convert non-JSON-safe dtypes
    for col in preview.columns:
        if pd.api.types.is_datetime64_any_dtype(preview[col]):
            preview[col] = preview[col].dt.strftime("%Y-%m-%dT%H:%M:%S").where(
                preview[col].notna(), None
            )

    # Replace NaN with None (JSON null)
    rows: list[dict[str, Any]] = []
    for record in preview.to_dict(orient="records"):
        clean_record: dict[str, Any] = {}
        for k, v in record.items():
            if v != v:  # NaN check (float NaN is not equal to itself)
                clean_record[k] = None
            elif isinstance(v, float) and (v == float("inf") or v == float("-inf")):
                clean_record[k] = None
            else:
                clean_record[k] = v
        rows.append(clean_record)

    return rows, list(df.columns)


def synthesize_plain_english_summary(
    plan: Plan,
    step_results: list[ExecutionResult],
    validation: ValidationResult | None,
) -> str:
    """Compose a plain-English summary from actual execution telemetry.

    This function is built exclusively from structured execution data —
    not from generic templates or hardcoded phrases. Every sentence is
    grounded in a real ExecutionResult or ValidationResult field.

    Args:
        plan: The Plan that was executed.
        step_results: Telemetry from execute_plan() — one entry per step.
        validation: The ValidationResult from validate(), or None if not run.

    Returns:
        A human-readable string summarising what was done and what changed.
    """
    if not step_results:
        return "No steps were executed."

    parts: list[str] = []

    # --- What ran ---
    successful = [r for r in step_results if r.success]
    failed = [r for r in step_results if not r.success]

    if successful:
        # Sentence 1: overall row transformation (tabular only)
        first = successful[0]
        last = successful[-1]
        if first.rows_before > 0 or last.rows_after > 0:
            if first.rows_before != last.rows_after:
                delta = first.rows_before - last.rows_after
                direction = "reduced" if delta > 0 else "increased"
                parts.append(
                    f"Processed {first.rows_before:,} rows → "
                    f"{last.rows_after:,} rows ({direction} by {abs(delta):,})."
                )
            else:
                parts.append(f"Processed {first.rows_before:,} rows (row count unchanged).")

        # Sentence 2+: per-step summaries (use the tool's own summary string)
        for r in successful:
            if r.summary:
                parts.append(f"• {r.summary}")

    # --- What failed ---
    if failed:
        fail_names = ", ".join(r.tool_name for r in failed)
        parts.append(
            f"The following step(s) did not complete successfully: {fail_names}."
        )
        for r in failed:
            if r.error_message:
                parts.append(f"  – {r.tool_name}: {r.error_message}")

    # --- Validation outcome ---
    if validation is not None:
        if validation.is_valid:
            parts.append(
                f"All {len(validation.checks_passed)} validation checks passed."
            )
        else:
            failed_checks = ", ".join(validation.checks_failed)
            parts.append(
                f"Validation flagged {len(validation.checks_failed)} issue(s): {failed_checks}."
            )
            if validation.can_retry:
                parts.append(
                    f"The pipeline retried the plan "
                    f"(attempt {validation.retry_count + 1} of {validation.max_retries + 1})."
                )

    return " ".join(parts) if parts else "Pipeline completed with no output."
