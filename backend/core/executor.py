"""DataWise Stage 4 — Execution Layer.

Dispatches each Step in a Plan to its registered tool-layer function, captures
per-step telemetry, and returns a list of ExecutionResult objects together with
the final transformed DataFrame.

ARCHITECTURE CONTRACT (decision.md — FIX F2):
- This module is COMPLETELY STATELESS and ORCHESTRATION-FREE.
- execute_plan() does ONE thing: run every step and return results.
- No retry logic, no planner calls, no conditional loops. Those live in
  backend/core/pipeline.py.
- The LLM NEVER touches data here; only allow-listed pure functions are called.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd

from backend.core.exceptions import DataWiseError, ExecutionError, ToolInputError
from backend.models.schemas import ExecutionResult, Plan, Step

# ---------------------------------------------------------------------------
# Tool registry — allow-list mapping tool_name -> callable
# Every function reachable by the executor must be declared here explicitly.
# Adding a new tool requires a deliberate entry; arbitrary function discovery
# is intentionally forbidden (defense-in-depth against plan-injection attacks).
# ---------------------------------------------------------------------------

import backend.tools.clean as _clean
import backend.tools.transform as _transform
import backend.tools.aggregate as _aggregate
import backend.tools.chart as _chart

_TOOL_REGISTRY: dict[str, Any] = {
    # --- Clean ---
    "drop_duplicates": _clean.drop_duplicates,
    "handle_missing": _clean.handle_missing,
    "fix_type_mismatches": _clean.fix_type_mismatches,
    "standardize_dates": _clean.standardize_dates,
    # --- Transform ---
    "drop_column": _transform.drop_column,
    "add_column": _transform.add_column,
    "select_columns": _transform.select_columns,
    "rename_columns": _transform.rename_columns,
    "filter_rows": _transform.filter_rows,
    "add_derived_column": _transform.add_derived_column,
    # --- Aggregate ---
    "groupby_aggregate": _aggregate.groupby_aggregate,
    "sort_values": _aggregate.sort_values,
    "top_n": _aggregate.top_n,
    # --- Chart ---
    "bar_chart": _chart.bar_chart,
    "line_chart": _chart.line_chart,
    "pie_chart": _chart.pie_chart,
}

# Chart tools that return a Path instead of a DataFrame.
_CHART_TOOLS = {"bar_chart", "line_chart", "pie_chart"}

# Tools whose return value is (df, extra_telemetry).
_TUPLE_RETURN_TOOLS = {"drop_duplicates", "handle_missing", "filter_rows"}


class ExecutorError(ExecutionError):
    """Raised when the executor encounters an unrecoverable dispatch error."""


def list_registered_tools() -> list[str]:
    """Return the sorted list of allowed tool names.

    Intended for use by planners and tests to confirm registry contents.
    """
    return sorted(_TOOL_REGISTRY.keys())


def _dispatch_step(
    df: pd.DataFrame,
    step: Step,
    output_dir: Path | None,
) -> tuple[pd.DataFrame, list[str], str]:
    """Dispatch a single Step to its registered tool function.

    Args:
        df: Current working DataFrame.
        step: The Step schema object containing tool_name and parameters.
        output_dir: Directory for chart output files.

    Returns:
        Tuple of (result_df, chart_paths, summary).

    Raises:
        ExecutorError: If tool_name is not in the registry.
        ToolInputError: Re-raised transparently from tool functions.
    """
    tool_name = step.tool_name
    params = dict(step.parameters)  # shallow copy — never mutate the Step

    if tool_name not in _TOOL_REGISTRY:
        raise ExecutorError(
            f"Unknown tool '{tool_name}'. Registered tools: {list_registered_tools()}",
            details=f"Step {step.step_number}: {step.description}",
        )

    func = _TOOL_REGISTRY[tool_name]
    result_df = df
    chart_paths: list[str] = []
    summary = step.description

    # ----------------------------------------------------------------
    # Chart tools: receive df + params + output_dir, return a Path.
    # They do NOT mutate the DataFrame.
    # ----------------------------------------------------------------
    if tool_name in _CHART_TOOLS:
        if output_dir is not None:
            params.setdefault("output_dir", output_dir)
        chart_path: Path = func(df, **params)
        chart_paths.append(str(chart_path))
        summary = (
            f"Generated {tool_name.replace('_', ' ')} "
            f"saved to {chart_path.name}."
        )
        return result_df, chart_paths, summary

    # ----------------------------------------------------------------
    # drop_duplicates -> (df, n_removed: int)
    # ----------------------------------------------------------------
    if tool_name == "drop_duplicates":
        result_df, n_removed = func(df, **params)
        summary = f"Removed {n_removed} duplicate row(s)."
        return result_df, chart_paths, summary

    # ----------------------------------------------------------------
    # handle_missing -> (df, n_filled: dict[str, int])
    # ----------------------------------------------------------------
    if tool_name == "handle_missing":
        result_df, n_filled = func(df, **params)
        filled_summary = ", ".join(
            f"{col}: {count}" for col, count in n_filled.items()
        )
        summary = f"Handled missing values ({filled_summary})."
        return result_df, chart_paths, summary

    # ----------------------------------------------------------------
    # filter_rows -> (df, n_removed: int)
    # ----------------------------------------------------------------
    if tool_name == "filter_rows":
        result_df, n_removed = func(df, **params)
        summary = f"Filtered rows: {n_removed} row(s) removed by condition."
        return result_df, chart_paths, summary

    # ----------------------------------------------------------------
    # Remaining tools: fix_type_mismatches, standardize_dates,
    # rename_columns, add_derived_column, groupby_aggregate,
    # sort_values, top_n — all return a plain DataFrame.
    # ----------------------------------------------------------------
    result_df = func(df, **params)
    return result_df, chart_paths, summary


def execute_plan(
    df: pd.DataFrame,
    plan: Plan,
    output_dir: Path | None = None,
) -> tuple[pd.DataFrame, list[ExecutionResult], list[str]]:
    """Execute every step in a Plan sequentially and return telemetry.

    STATELESS CONTRACT:
    - Accepts a DataFrame and Plan; returns transformed DataFrame + results.
    - Performs NO retry logic, NO planner calls, NO loops beyond iterating
      plan.steps exactly once.
    - On error, appends a failed ExecutionResult then re-raises so that
      pipeline.py can decide on retry strategy.

    Args:
        df: The input DataFrame to transform (copied before mutation).
        plan: The Plan produced by Stage 3 (TaskPlanner).
        output_dir: Optional directory where chart artifacts are written.

    Returns:
        Tuple of:
          - final_df: The DataFrame after all steps were applied.
          - results: List of ExecutionResult, one per step, in order.
          - chart_paths: All chart file paths generated across all steps.

    Raises:
        ExecutorError: If an unknown tool is referenced in the plan, or on
                       unexpected internal errors.
        ToolInputError: Propagated unchanged from the tool layer.
    """
    current_df = df.copy()
    results: list[ExecutionResult] = []
    all_chart_paths: list[str] = []

    for step in plan.steps:
        rows_before = len(current_df)
        cols_before = len(current_df.columns)
        start_ts = time.monotonic()
        success = False
        error_message: str | None = None
        step_chart_paths: list[str] = []
        summary = step.description

        try:
            current_df, step_chart_paths, summary = _dispatch_step(
                current_df, step, output_dir
            )
            all_chart_paths.extend(step_chart_paths)
            success = True

        except (ToolInputError, ExecutorError) as exc:
            error_message = str(exc)
            summary = f"Step {step.step_number} failed: {error_message}"
            result = ExecutionResult(
                step_number=step.step_number,
                tool_name=step.tool_name,
                success=False,
                rows_before=rows_before,
                rows_after=len(current_df),
                columns_before=cols_before,
                columns_after=len(current_df.columns),
                summary=summary,
                error_message=error_message,
                execution_time_ms=round((time.monotonic() - start_ts) * 1000, 2),
            )
            results.append(result)
            raise

        except Exception as exc:
            error_message = (
                f"Unexpected error in step {step.step_number} "
                f"('{step.tool_name}'): {exc!s}"
            )
            summary = error_message
            result = ExecutionResult(
                step_number=step.step_number,
                tool_name=step.tool_name,
                success=False,
                rows_before=rows_before,
                rows_after=len(current_df),
                columns_before=cols_before,
                columns_after=len(current_df.columns),
                summary=summary,
                error_message=error_message,
                execution_time_ms=round((time.monotonic() - start_ts) * 1000, 2),
            )
            results.append(result)
            raise ExecutorError(error_message) from exc

        elapsed_ms = round((time.monotonic() - start_ts) * 1000, 2)
        results.append(
            ExecutionResult(
                step_number=step.step_number,
                tool_name=step.tool_name,
                success=success,
                rows_before=rows_before,
                rows_after=len(current_df),
                columns_before=cols_before,
                columns_after=len(current_df.columns),
                summary=summary,
                error_message=error_message,
                execution_time_ms=elapsed_ms,
            )
        )

    return current_df, results, all_chart_paths
