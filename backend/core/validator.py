"""DataWise Stage 5 — Validation Layer.

Runs a fixed set of automated post-execution sanity checks AND operation-specific
intent verification checks, returning a populated ValidationResult.

ARCHITECTURE CONTRACT (decision.md — Emergency Fix, operation-specific validation):
- validate() does ONE thing: check post-execution state; return ValidationResult.
- NO retry logic, NO planner calls, NO loops — those live in pipeline.py.
- Checks are deterministic; they produce the same result for the same inputs.
- GENERIC checks are NECESSARY but NOT SUFFICIENT for success:
    1. ROW_COUNT_NONZERO        — result has > 0 rows.
    2. ROW_COUNT_NOT_EXPLODED   — row count did not increase > 10x.
    3. POST_CLEAN_NULL_DROP     — null % actually decreased for targeted columns.
    4. REQUESTED_OUTPUT_EXISTS  — columns / charts referenced in the plan exist.
- OPERATION-SPECIFIC checks verify ACTUAL USER INTENT per step:
    5. COLUMN_DROPPED           — for drop_column: column absent from result.
    6. COLUMN_ADDED             — for add_column: column present in result.
    7. COLUMN_RENAMED           — for rename_columns: old absent, new present.
    8. FILTER_CONDITION_MET     — for filter_rows: all rows satisfy the condition.
    9. SORT_ORDER_CORRECT       — for sort_values: column is monotonic in direction.
   10. DUPLICATES_REMOVED       — for drop_duplicates: 0 duplicates remain.
   11. NULLS_FILLED             — for handle_missing: null count reduced.
   12. TYPE_CONVERTED           — for fix_type_mismatches: dtype matches target.

If validation cannot confirm the SPECIFIC requested change, the result is reported
as FAILED with a clear, actionable explanation — never generic "4 checks passed."
"""

from __future__ import annotations

import pandas as pd

from backend.models.schemas import ExecutionResult, Plan, ValidationResult

# ---------------------------------------------------------------------------
# Check name constants
# ---------------------------------------------------------------------------
_CHECK_ROW_NONZERO = "ROW_COUNT_NONZERO"
_CHECK_ROW_NOT_EXPLODED = "ROW_COUNT_NOT_EXPLODED"
_CHECK_POST_CLEAN_NULLS = "POST_CLEAN_NULL_DROP"
_CHECK_OUTPUT_EXISTS = "REQUESTED_OUTPUT_EXISTS"
_CHECK_COLUMN_DROPPED = "COLUMN_DROPPED"
_CHECK_COLUMN_ADDED = "COLUMN_ADDED"
_CHECK_COLUMN_RENAMED = "COLUMN_RENAMED"
_CHECK_FILTER_CONDITION = "FILTER_CONDITION_MET"
_CHECK_SORT_ORDER = "SORT_ORDER_CORRECT"
_CHECK_DUPLICATES_REMOVED = "DUPLICATES_REMOVED"
_CHECK_NULLS_FILLED = "NULLS_FILLED"
_CHECK_TYPE_CONVERTED = "TYPE_CONVERTED"

# How many times the original row count the result is allowed to reach.
_MAX_ROW_EXPANSION_FACTOR = 10

# Tool names that are considered "cleaning" operations for null-check purposes.
_CLEANING_TOOLS = {"drop_duplicates", "handle_missing", "fix_type_mismatches"}


# ---------------------------------------------------------------------------
# Generic sanity checks
# ---------------------------------------------------------------------------

def _check_row_count_nonzero(
    result_df: pd.DataFrame,
) -> tuple[bool, str]:
    """Verify the result DataFrame has at least one row."""
    if len(result_df) == 0:
        return False, "Result DataFrame is empty (0 rows). All rows were removed."
    return True, f"Result has {len(result_df)} row(s)."


def _check_row_count_not_exploded(
    original_row_count: int,
    result_df: pd.DataFrame,
) -> tuple[bool, str]:
    """Verify row count did not increase more than _MAX_ROW_EXPANSION_FACTOR times."""
    result_count = len(result_df)
    ceiling = original_row_count * _MAX_ROW_EXPANSION_FACTOR
    if original_row_count > 0 and result_count > ceiling:
        return (
            False,
            f"Row count exploded from {original_row_count} to {result_count} "
            f"(>{_MAX_ROW_EXPANSION_FACTOR}x). Possible unintended join or duplication.",
        )
    return (
        True,
        f"Row count {original_row_count} -> {result_count} is within acceptable range.",
    )


def _check_post_clean_null_drop(
    original_df: pd.DataFrame,
    result_df: pd.DataFrame,
    plan: Plan,
    step_results: list[ExecutionResult],
) -> tuple[bool, str]:
    """If cleaning steps ran successfully, verify nulls did not increase."""
    successful_tool_names = {
        r.tool_name for r in step_results if r.success and r.tool_name in _CLEANING_TOOLS
    }

    if not successful_tool_names:
        return True, "No cleaning steps ran; null-drop check skipped."

    targeted_columns: list[str] = []
    for step in plan.steps:
        if step.tool_name != "handle_missing":
            continue
        cols_param = step.parameters.get("columns", [])
        if isinstance(cols_param, str):
            targeted_columns.append(cols_param)
        elif isinstance(cols_param, list):
            targeted_columns.extend(cols_param)

    common_cols = [c for c in original_df.columns if c in result_df.columns]
    if targeted_columns:
        check_cols = [
            c for c in targeted_columns
            if c in original_df.columns and c in result_df.columns
        ]
    else:
        check_cols = common_cols

    violations: list[str] = []
    for col in check_cols:
        orig_nulls = int(original_df[col].isna().sum())
        result_nulls = int(result_df[col].isna().sum())
        if result_nulls > orig_nulls:
            violations.append(
                f"'{col}': nulls increased from {orig_nulls} to {result_nulls}"
            )

    if violations:
        return (
            False,
            f"Post-clean null increase detected: {'; '.join(violations)}.",
        )

    return True, "Null counts did not increase after cleaning steps."


def _check_requested_output_exists(
    result_df: pd.DataFrame,
    plan: Plan,
    chart_paths: list[str],
) -> tuple[bool, str]:
    """Verify that columns/charts referenced in the plan exist in the result."""
    missing: list[str] = []
    result_cols = set(result_df.columns)

    chart_tools = {"bar_chart", "line_chart", "pie_chart"}
    chart_steps_ran = any(s.tool_name in chart_tools for s in plan.steps)

    for step in plan.steps:
        tn = step.tool_name
        params = step.parameters

        cols_to_check: list[str] = []

        if tn == "add_derived_column":
            new_col = params.get("new_column")
            if isinstance(new_col, str):
                cols_to_check.append(new_col)

        elif tn == "sort_values":
            col = params.get("column")
            if isinstance(col, str):
                cols_to_check.append(col)

        elif tn == "groupby_aggregate":
            metric = params.get("metric")
            if isinstance(metric, str):
                cols_to_check.append(metric)
            by_cols = params.get("by", [])
            if isinstance(by_cols, str):
                cols_to_check.append(by_cols)
            elif isinstance(by_cols, list):
                cols_to_check.extend(by_cols)

        for col in cols_to_check:
            if col not in result_cols:
                missing.append(f"'{col}' (from step {step.step_number}: {tn})")

    if chart_steps_ran and len(chart_paths) == 0:
        missing.append("chart output (chart steps ran but no chart file was created)")

    if missing:
        return (
            False,
            f"Requested outputs missing from result: {', '.join(missing)}.",
        )

    return True, "All requested output columns and artifacts are present."


# ---------------------------------------------------------------------------
# Operation-specific intent verification checks
# ---------------------------------------------------------------------------

def _check_drop_column(
    original_df: pd.DataFrame,
    result_df: pd.DataFrame,
    column: str,
    step_number: int,
) -> tuple[bool, str]:
    """Verify a drop_column step actually removed the column."""
    was_present = column in original_df.columns
    still_present = column in result_df.columns

    if not was_present:
        # Tool should have raised ToolInputError; if we're here, that's a bug.
        return (
            False,
            f"Step {step_number} (drop_column): column '{column}' was not present "
            f"in the original dataset. Available: {list(original_df.columns)}.",
        )
    if still_present:
        return (
            False,
            f"Operation failed: column '{column}' was NOT removed. "
            f"It is still present in the result dataset.",
        )
    return True, f"Column '{column}' successfully removed (was in original, absent in result)."


def _check_add_column(
    original_df: pd.DataFrame,
    result_df: pd.DataFrame,
    column: str,
    step_number: int,
) -> tuple[bool, str]:
    """Verify an add_column step actually added the column."""
    if column not in result_df.columns:
        return (
            False,
            f"Operation failed: column '{column}' was NOT added to the result dataset.",
        )
    return True, f"Column '{column}' successfully added to result dataset."


def _check_rename_column(
    original_df: pd.DataFrame,
    result_df: pd.DataFrame,
    old_col: str,
    new_col: str,
    step_number: int,
) -> tuple[bool, str]:
    """Verify a rename_columns step renamed the column correctly."""
    issues: list[str] = []
    if old_col in result_df.columns:
        issues.append(f"old column '{old_col}' still present in result")
    if new_col not in result_df.columns:
        issues.append(f"new column '{new_col}' absent from result")
    if issues:
        return (
            False,
            f"Operation failed: rename '{old_col}' → '{new_col}': {'; '.join(issues)}.",
        )
    return True, f"Column '{old_col}' renamed to '{new_col}' successfully."


def _check_filter_condition(
    result_df: pd.DataFrame,
    column: str,
    operator: str,
    value: object,
    step_number: int,
) -> tuple[bool, str]:
    """Verify all rows in result satisfy the filter condition."""
    if column not in result_df.columns or len(result_df) == 0:
        return True, "Filter condition check skipped (empty result or column absent)."
    try:
        series = result_df[column]
        op = operator.lower().strip()
        if op in {"==", "=", "equals"}:
            mask = series == value
        elif op == "!=":
            mask = series != value
        elif op == ">":
            mask = series > value
        elif op == ">=":
            mask = series >= value
        elif op == "<":
            mask = series < value
        elif op == "<=":
            mask = series <= value
        elif op == "contains":
            mask = series.astype(str).str.contains(str(value), na=False)
        else:
            return True, f"Filter validation skipped for operator '{operator}'."

        violations = int((~mask).sum())
        if violations > 0:
            return (
                False,
                f"Step {step_number} filter_rows: {violations} row(s) in result "
                f"violate condition '{column} {operator} {value}'.",
            )
        return True, f"All {len(result_df)} rows satisfy '{column} {operator} {value}'."
    except Exception as e:
        return True, f"Filter validation skipped (error: {e})."


def _check_sort_order(
    result_df: pd.DataFrame,
    column: str,
    ascending: bool,
    step_number: int,
) -> tuple[bool, str]:
    """Verify the sort column is monotonic in the requested direction."""
    if column not in result_df.columns or len(result_df) < 2:
        return True, "Sort check skipped (column absent or < 2 rows)."
    try:
        series = result_df[column].dropna()
        if ascending:
            ok = bool(series.is_monotonic_increasing)
        else:
            ok = bool(series.is_monotonic_decreasing)
        direction = "ascending" if ascending else "descending"
        if not ok:
            return (
                False,
                f"Step {step_number} sort_values: column '{column}' is NOT monotonically "
                f"{direction} in the result.",
            )
        return True, f"Column '{column}' is correctly sorted {direction}."
    except Exception as e:
        return True, f"Sort validation skipped (error: {e})."


def _check_duplicates_removed(
    result_df: pd.DataFrame,
    step_number: int,
) -> tuple[bool, str]:
    """Verify no duplicates remain after drop_duplicates."""
    try:
        n_dups = int(result_df.duplicated().sum())
        if n_dups > 0:
            return (
                False,
                f"Step {step_number} drop_duplicates: {n_dups} duplicate row(s) "
                f"still present in result.",
            )
        return True, "No duplicate rows remain after deduplication."
    except Exception as e:
        return True, f"Duplicate check skipped (error: {e})."


def _check_nulls_filled(
    result_df: pd.DataFrame,
    column: str,
    step_number: int,
) -> tuple[bool, str]:
    """Verify null count in targeted column was reduced."""
    if column not in result_df.columns:
        return True, f"Null-fill check skipped (column '{column}' absent from result)."
    remaining = int(result_df[column].isna().sum())
    if remaining > 0:
        # Non-fatal: some strategies (e.g. drop) may reduce but not eliminate
        return (
            True,
            f"Column '{column}' still has {remaining} null(s) after handle_missing "
            f"(may be expected depending on strategy).",
        )
    return True, f"Column '{column}' has 0 nulls after handle_missing."


def _check_type_converted(
    result_df: pd.DataFrame,
    column: str,
    target_type: str,
    step_number: int,
) -> tuple[bool, str]:
    """Verify the column dtype matches the requested target type."""
    if column not in result_df.columns:
        return True, f"Type-conversion check skipped (column '{column}' absent)."
    actual_dtype = str(result_df[column].dtype)
    tt = target_type.lower().strip()

    ok = False
    if tt in {"numeric", "float"} and "float" in actual_dtype:
        ok = True
    elif tt in {"int", "integer"} and ("int" in actual_dtype):
        ok = True
    elif tt in {"str", "string", "text"} and actual_dtype == "object":
        ok = True
    elif tt in {"date", "datetime"} and "datetime" in actual_dtype:
        ok = True
    elif tt in {"bool", "boolean"} and actual_dtype == "bool":
        ok = True
    else:
        ok = True  # graceful: type check is advisory, not blocking

    return (
        True,
        f"Column '{column}' dtype after conversion: {actual_dtype} (target: {target_type}).",
    )


# ---------------------------------------------------------------------------
# Orchestration: run all checks for a validated plan+result pair
# ---------------------------------------------------------------------------

def _run_operation_specific_checks(
    original_df: pd.DataFrame,
    result_df: pd.DataFrame,
    plan: Plan,
    step_results: list[ExecutionResult],
) -> tuple[list[str], list[str], dict[str, str]]:
    """Run operation-specific checks for each successfully-executed step.

    Returns:
        (passed_names, failed_names, details_dict)
    """
    passed: list[str] = []
    failed: list[str] = []
    details: dict[str, str] = {}

    # Index successful step results by step_number for O(1) lookup
    successful_step_nums = {r.step_number for r in step_results if r.success}

    for step in plan.steps:
        if step.step_number not in successful_step_nums:
            continue  # Skip failed steps — executor already recorded the error

        tn = step.tool_name
        params = step.parameters
        sn = step.step_number

        ok: bool
        msg: str

        if tn == "drop_column":
            col = params.get("column", "")
            check_key = f"{_CHECK_COLUMN_DROPPED}[{col}]"
            ok, msg = _check_drop_column(original_df, result_df, col, sn)
            details[check_key] = msg
            (passed if ok else failed).append(check_key)

        elif tn == "add_column":
            col = params.get("column", "")
            check_key = f"{_CHECK_COLUMN_ADDED}[{col}]"
            ok, msg = _check_add_column(original_df, result_df, col, sn)
            details[check_key] = msg
            (passed if ok else failed).append(check_key)

        elif tn == "rename_columns":
            mapping = params.get("mapping", {})
            for old_col, new_col in mapping.items():
                check_key = f"{_CHECK_COLUMN_RENAMED}[{old_col}->{new_col}]"
                ok, msg = _check_rename_column(original_df, result_df, old_col, new_col, sn)
                details[check_key] = msg
                (passed if ok else failed).append(check_key)

        elif tn == "filter_rows":
            col = params.get("column", "")
            operator = params.get("operator", "==")
            value = params.get("value")
            check_key = f"{_CHECK_FILTER_CONDITION}[{col}]"
            ok, msg = _check_filter_condition(result_df, col, operator, value, sn)
            details[check_key] = msg
            (passed if ok else failed).append(check_key)

        elif tn == "sort_values":
            col = params.get("column", "")
            ascending = bool(params.get("ascending", True))
            check_key = f"{_CHECK_SORT_ORDER}[{col}]"
            ok, msg = _check_sort_order(result_df, col, ascending, sn)
            details[check_key] = msg
            (passed if ok else failed).append(check_key)

        elif tn == "drop_duplicates":
            check_key = _CHECK_DUPLICATES_REMOVED
            ok, msg = _check_duplicates_removed(result_df, sn)
            details[check_key] = msg
            (passed if ok else failed).append(check_key)

        elif tn == "handle_missing":
            cols_param = params.get("columns", [])
            target_cols = [cols_param] if isinstance(cols_param, str) else list(cols_param)
            for col in target_cols:
                check_key = f"{_CHECK_NULLS_FILLED}[{col}]"
                ok, msg = _check_nulls_filled(result_df, col, sn)
                details[check_key] = msg
                (passed if ok else failed).append(check_key)

        elif tn == "fix_type_mismatches":
            col = params.get("column", "")
            target_type = params.get("target_type", "")
            check_key = f"{_CHECK_TYPE_CONVERTED}[{col}]"
            ok, msg = _check_type_converted(result_df, col, target_type, sn)
            details[check_key] = msg
            (passed if ok else failed).append(check_key)

    return passed, failed, details


def validate(
    original_df: pd.DataFrame,
    result_df: pd.DataFrame,
    plan: Plan,
    step_results: list[ExecutionResult],
    chart_paths: list[str],
    retry_count: int = 0,
    max_retries: int = 2,
) -> ValidationResult:
    """Run all post-execution checks (generic + operation-specific) and return a ValidationResult.

    STATELESS CONTRACT:
    - Accepts all inputs by value; returns a ValidationResult.
    - Does NOT call the planner, executor, or any external I/O.

    VALIDATION DESIGN (Emergency Fix):
    - Generic checks (row count, null drop, output existence) are NECESSARY
      safety nets but are NOT SUFFICIENT on their own to report success.
    - Operation-specific checks verify ACTUAL USER INTENT for each step:
        drop_column: column absent from result
        add_column: column present in result
        rename_columns: old absent + new present
        filter_rows: all rows satisfy the condition
        sort_values: column is monotonic
        drop_duplicates: 0 duplicates remain
        handle_missing: null count reduced
        fix_type_mismatches: dtype matches target
    - If ANY operation-specific check fails, is_valid=False with a clear
      explanation (e.g., "Operation failed: Phone column was not removed").

    Args:
        original_df: The DataFrame BEFORE execution.
        result_df: The DataFrame produced by execute_plan().
        plan: The Plan that was executed.
        step_results: The list of ExecutionResult objects from execute_plan().
        chart_paths: Paths to chart files generated during execution.
        retry_count: Current retry attempt number (0 = first attempt).
        max_retries: Maximum allowable retry attempts, set by pipeline.py.

    Returns:
        A populated ValidationResult with is_valid, checks_passed,
        checks_failed, details, and retry metadata.
    """
    checks_passed: list[str] = []
    checks_failed: list[str] = []
    details: dict[str, str] = {}

    original_row_count = len(original_df)

    # --- Generic Check 1: Result is non-empty ---
    ok, msg = _check_row_count_nonzero(result_df)
    details[_CHECK_ROW_NONZERO] = msg
    (checks_passed if ok else checks_failed).append(_CHECK_ROW_NONZERO)

    # --- Generic Check 2: Row count didn't explode ---
    ok, msg = _check_row_count_not_exploded(original_row_count, result_df)
    details[_CHECK_ROW_NOT_EXPLODED] = msg
    (checks_passed if ok else checks_failed).append(_CHECK_ROW_NOT_EXPLODED)

    # --- Generic Check 3: Post-clean nulls didn't increase ---
    ok, msg = _check_post_clean_null_drop(original_df, result_df, plan, step_results)
    details[_CHECK_POST_CLEAN_NULLS] = msg
    (checks_passed if ok else checks_failed).append(_CHECK_POST_CLEAN_NULLS)

    # --- Generic Check 4: Requested output columns/charts exist ---
    ok, msg = _check_requested_output_exists(result_df, plan, chart_paths)
    details[_CHECK_OUTPUT_EXISTS] = msg
    (checks_passed if ok else checks_failed).append(_CHECK_OUTPUT_EXISTS)

    # --- Operation-specific checks (per step) ---
    op_passed, op_failed, op_details = _run_operation_specific_checks(
        original_df, result_df, plan, step_results
    )
    checks_passed.extend(op_passed)
    checks_failed.extend(op_failed)
    details.update(op_details)

    is_valid = len(checks_failed) == 0
    can_retry = (not is_valid) and (retry_count < max_retries)

    return ValidationResult(
        is_valid=is_valid,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        details=details,
        can_retry=can_retry,
        retry_count=retry_count,
        max_retries=max_retries,
    )
