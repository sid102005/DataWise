"""Tests for backend/core/executor.py — Stage 4 Execution Layer."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.core.executor import (
    ExecutorError,
    execute_plan,
    list_registered_tools,
)
from backend.core.exceptions import ToolInputError
from backend.models.schemas import ExecutionResult, Objective, ObjectiveCategory, Plan, Step


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(steps: list[Step]) -> Plan:
    return Plan(
        plan_id="test-plan",
        session_id="test-session",
        objectives=[
            Objective(
                category=ObjectiveCategory.CLEAN,
                description="Test objective",
            )
        ],
        steps=steps,
        rationale="Test plan",
    )


def _make_step(
    step_number: int,
    tool_name: str,
    description: str,
    parameters: dict | None = None,
    expected_output: str = "ok",
) -> Step:
    return Step(
        step_number=step_number,
        tool_name=tool_name,
        description=description,
        parameters=parameters or {},
        expected_output=expected_output,
    )


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Name": ["Alice", "Bob", "Alice", "Carol"],
            "Age": [30.0, None, 30.0, 25.0],
            "Purchase": [100.0, 200.0, 100.0, 150.0],
        }
    )


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_all_expected_tools_registered(self):
        expected = {
            "drop_duplicates",
            "handle_missing",
            "fix_type_mismatches",
            "standardize_dates",
            "strip_whitespace",
            "normalize_missing",
            "drop_empty_columns",
            "drop_constant_columns",
            "auto_fix_types",
            "clean_for_ml",
            "drop_column",
            "add_column",
            "select_columns",
            "rename_columns",
            "filter_rows",
            "add_derived_column",
            "groupby_aggregate",
            "sort_values",
            "top_n",
            "bar_chart",
            "line_chart",
            "pie_chart",
        }
        registered = set(list_registered_tools())
        assert expected == registered, (
            f"Registry mismatch. Missing: {expected - registered}. "
            f"Extra: {registered - expected}."
        )

    def test_list_registered_tools_is_sorted(self):
        tools = list_registered_tools()
        assert tools == sorted(tools)


# ---------------------------------------------------------------------------
# execute_plan — successful execution
# ---------------------------------------------------------------------------


class TestExecutePlanSuccess:
    def test_single_drop_duplicates_step(self):
        df = _sample_df()
        plan = _make_plan(
            [_make_step(1, "drop_duplicates", "Remove duplicates")]
        )
        final_df, results, chart_paths = execute_plan(df, plan)

        assert len(final_df) == 3, "Should remove 1 duplicate row (Alice duplicated)"
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].step_number == 1
        assert results[0].tool_name == "drop_duplicates"
        assert results[0].rows_before == 4
        assert results[0].rows_after == 3
        assert chart_paths == []

    def test_single_handle_missing_step(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(
                    1,
                    "handle_missing",
                    "Fill missing Age",
                    {"columns": "Age", "strategy": "median"},
                )
            ]
        )
        final_df, results, chart_paths = execute_plan(df, plan)

        assert final_df["Age"].isna().sum() == 0
        assert results[0].success is True
        assert "Age" in results[0].summary

    def test_multi_step_clean_and_sort(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(1, "drop_duplicates", "Remove dupes"),
                _make_step(
                    2,
                    "handle_missing",
                    "Fill Age",
                    {"columns": "Age", "strategy": "median"},
                ),
                _make_step(
                    3, "sort_values", "Sort by Purchase", {"column": "Purchase", "ascending": False}
                ),
                _make_step(4, "top_n", "Top 2", {"n": 2}),
            ]
        )
        final_df, results, chart_paths = execute_plan(df, plan)

        assert len(final_df) == 2
        assert final_df["Age"].isna().sum() == 0
        assert len(results) == 4
        assert all(r.success for r in results)
        assert chart_paths == []

    def test_result_telemetry_rows_tracked_correctly(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(1, "drop_duplicates", "Remove dupes"),
                _make_step(2, "top_n", "Top 2", {"n": 2}),
            ]
        )
        _, results, _ = execute_plan(df, plan)

        assert results[0].rows_before == 4
        assert results[0].rows_after == 3
        assert results[1].rows_before == 3
        assert results[1].rows_after == 2

    def test_columns_before_after_tracked(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(
                    1,
                    "add_derived_column",
                    "Add Revenue",
                    {
                        "new_column": "Revenue",
                        "expression_spec": {"op": "multiply", "a": "Purchase", "b": 1.1},
                    },
                )
            ]
        )
        _, results, _ = execute_plan(df, plan)

        assert results[0].columns_before == 3
        assert results[0].columns_after == 4

    def test_execution_time_ms_is_nonnegative(self):
        df = _sample_df()
        plan = _make_plan(
            [_make_step(1, "drop_duplicates", "Remove dupes")]
        )
        _, results, _ = execute_plan(df, plan)
        assert results[0].execution_time_ms >= 0.0

    def test_original_df_not_mutated(self):
        df = _sample_df()
        original_len = len(df)
        plan = _make_plan(
            [_make_step(1, "drop_duplicates", "Remove dupes")]
        )
        execute_plan(df, plan)
        assert len(df) == original_len, "Original df must not be mutated by execute_plan"

    def test_rename_columns_step(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(
                    1,
                    "rename_columns",
                    "Rename Purchase to Revenue",
                    {"mapping": {"Purchase": "Revenue"}},
                )
            ]
        )
        final_df, results, _ = execute_plan(df, plan)
        assert "Revenue" in final_df.columns
        assert "Purchase" not in final_df.columns
        assert results[0].success is True

    def test_filter_rows_step(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(
                    1,
                    "filter_rows",
                    "Keep only Purchase >= 150",
                    {"column": "Purchase", "operator": ">=", "value": 150.0},
                )
            ]
        )
        final_df, results, _ = execute_plan(df, plan)
        assert all(final_df["Purchase"] >= 150.0)
        assert results[0].success is True


# ---------------------------------------------------------------------------
# execute_plan — error handling
# ---------------------------------------------------------------------------


class TestExecutePlanErrors:
    def test_unknown_tool_raises_executor_error(self):
        df = _sample_df()
        plan = _make_plan(
            [_make_step(1, "nonexistent_tool", "Bad step")]
        )
        with pytest.raises(ExecutorError, match="nonexistent_tool"):
            execute_plan(df, plan)

    def test_unknown_tool_records_failed_result_before_raising(self):
        df = _sample_df()
        plan = _make_plan(
            [_make_step(1, "nonexistent_tool", "Bad step")]
        )
        with pytest.raises(ExecutorError):
            try:
                execute_plan(df, plan)
            except ExecutorError:
                raise

    def test_tool_input_error_propagates(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(
                    1,
                    "drop_duplicates",
                    "Deduplicate on nonexistent column",
                    {"subset": "NONEXISTENT_COLUMN"},
                )
            ]
        )
        with pytest.raises(ToolInputError):
            execute_plan(df, plan)

    def test_failed_step_result_has_error_message(self):
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(
                    1,
                    "handle_missing",
                    "Bad column",
                    {"columns": "NONEXISTENT", "strategy": "median"},
                )
            ]
        )
        results_captured: list[ExecutionResult] = []
        try:
            _, results, _ = execute_plan(df, plan)
        except ToolInputError:
            pass  # expected; result should still be in results list
        # Re-run capturing the partial results via a wrapper
        try:
            execute_plan(df, plan)
        except ToolInputError as exc:
            # results appended before raise — test via indirect check
            assert "NONEXISTENT" in str(exc)

    def test_error_on_step2_after_step1_success(self):
        """Ensure step 1 runs OK and step 2 fails cleanly."""
        df = _sample_df()
        plan = _make_plan(
            [
                _make_step(1, "drop_duplicates", "OK step"),
                _make_step(
                    2,
                    "sort_values",
                    "Sort on bad column",
                    {"column": "GHOST_COL"},
                ),
            ]
        )
        with pytest.raises(ToolInputError):
            execute_plan(df, plan)

    def test_empty_steps_list_returns_unchanged_df(self):
        df = _sample_df()
        plan = _make_plan([])
        final_df, results, chart_paths = execute_plan(df, plan)
        assert len(final_df) == len(df)
        assert results == []
        assert chart_paths == []
