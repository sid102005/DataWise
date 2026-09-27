"""Tests for backend/core/validator.py — Stage 5 Validation Layer."""

from __future__ import annotations

import pandas as pd
import pytest

from backend.core.validator import validate
from backend.models.schemas import (
    ExecutionResult,
    Objective,
    ObjectiveCategory,
    Plan,
    Step,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plan(steps: list[Step]) -> Plan:
    return Plan(
        plan_id="val-test-plan",
        session_id="val-test-session",
        objectives=[
            Objective(
                category=ObjectiveCategory.CLEAN,
                description="Validate test",
            )
        ],
        steps=steps,
        rationale="Validator test plan",
    )


def _make_step(
    step_number: int,
    tool_name: str,
    description: str,
    parameters: dict | None = None,
) -> Step:
    return Step(
        step_number=step_number,
        tool_name=tool_name,
        description=description,
        parameters=parameters or {},
        expected_output="ok",
    )


def _make_exec_result(
    step_number: int,
    tool_name: str,
    success: bool = True,
    rows_before: int = 4,
    rows_after: int = 4,
) -> ExecutionResult:
    return ExecutionResult(
        step_number=step_number,
        tool_name=tool_name,
        success=success,
        rows_before=rows_before,
        rows_after=rows_after,
        columns_before=3,
        columns_after=3,
        summary="ok",
        error_message=None,
        execution_time_ms=1.0,
    )


def _base_original_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Name": ["Alice", "Bob", "Carol", "Dave"],
            "Age": [30.0, 25.0, 28.0, None],
            "Purchase": [100.0, 200.0, 150.0, 50.0],
        }
    )


# ---------------------------------------------------------------------------
# All-pass scenario
# ---------------------------------------------------------------------------


class TestValidateAllPass:
    def test_all_checks_pass_on_clean_result(self):
        original = _base_original_df()
        result = original.copy()
        result["Age"] = result["Age"].fillna(28.0)  # nulls gone
        # Sort by Purchase ascending — what sort_values would actually produce
        result = result.sort_values("Purchase", ascending=True).reset_index(drop=True)

        plan = _make_plan(
            [
                _make_step(1, "handle_missing", "Fill Age", {"columns": "Age", "strategy": "median"}),
                _make_step(2, "sort_values", "Sort by Purchase", {"column": "Purchase", "ascending": True}),
            ]
        )
        step_results = [
            _make_exec_result(1, "handle_missing"),
            _make_exec_result(2, "sort_values"),
        ]

        vr: ValidationResult = validate(
            original_df=original,
            result_df=result,
            plan=plan,
            step_results=step_results,
            chart_paths=[],
        )

        assert vr.is_valid is True
        assert vr.checks_failed == []
        # 4 generic + 1 NULLS_FILLED[Age] + 1 SORT_ORDER_CORRECT[Purchase]
        assert len(vr.checks_passed) == 6

    def test_valid_result_has_can_retry_false(self):
        original = _base_original_df()
        result = original.dropna().reset_index(drop=True)
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates")]
        vr = validate(original, result, plan, step_results, [], retry_count=0)
        assert vr.can_retry is False


# ---------------------------------------------------------------------------
# Check 1: ROW_COUNT_NONZERO
# ---------------------------------------------------------------------------


class TestRowCountNonzeroCheck:
    def test_empty_result_fails(self):
        original = _base_original_df()
        empty = pd.DataFrame(columns=original.columns)
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates", rows_after=0)]
        vr = validate(original, empty, plan, step_results, [])

        assert vr.is_valid is False
        assert "ROW_COUNT_NONZERO" in vr.checks_failed

    def test_single_row_result_passes(self):
        original = _base_original_df()
        single = original.head(1).reset_index(drop=True)
        plan = _make_plan([_make_step(1, "top_n", "Top 1", {"n": 1})])
        step_results = [_make_exec_result(1, "top_n", rows_after=1)]
        vr = validate(original, single, plan, step_results, [])
        assert "ROW_COUNT_NONZERO" in vr.checks_passed


# ---------------------------------------------------------------------------
# Check 2: ROW_COUNT_NOT_EXPLODED
# ---------------------------------------------------------------------------


class TestRowExplosionCheck:
    def test_explosion_beyond_10x_fails(self):
        original = _base_original_df()
        # 4 rows * 11 = 44 rows — exceeds 10x factor
        exploded = pd.concat([original] * 11, ignore_index=True)
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates", rows_after=len(exploded))]
        vr = validate(original, exploded, plan, step_results, [])

        assert vr.is_valid is False
        assert "ROW_COUNT_NOT_EXPLODED" in vr.checks_failed

    def test_exactly_10x_passes(self):
        original = _base_original_df()
        ten_x = pd.concat([original] * 10, ignore_index=True)
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates", rows_after=len(ten_x))]
        vr = validate(original, ten_x, plan, step_results, [])
        assert "ROW_COUNT_NOT_EXPLODED" in vr.checks_passed

    def test_zero_original_rows_skips_explosion_check(self):
        """Edge: original_row_count=0 should not divide-by-zero or fail."""
        empty_original = pd.DataFrame(columns=["Age"])
        result = pd.DataFrame({"Age": [1, 2, 3]})
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates")]
        vr = validate(empty_original, result, plan, step_results, [])
        # Should not raise; explosion check passes when original=0
        assert "ROW_COUNT_NOT_EXPLODED" in vr.checks_passed


# ---------------------------------------------------------------------------
# Check 3: POST_CLEAN_NULL_DROP
# ---------------------------------------------------------------------------


class TestPostCleanNullDropCheck:
    def test_nulls_decreased_passes(self):
        original = _base_original_df()          # Age has 1 null
        result = original.copy()
        result["Age"] = result["Age"].fillna(28.0)   # nulls gone
        plan = _make_plan(
            [_make_step(1, "handle_missing", "Fill Age", {"columns": "Age"})]
        )
        step_results = [_make_exec_result(1, "handle_missing")]
        vr = validate(original, result, plan, step_results, [])
        assert "POST_CLEAN_NULL_DROP" in vr.checks_passed

    def test_nulls_increased_fails(self):
        original = _base_original_df()          # Age has 1 null
        result = original.copy()
        result["Age"] = None                     # all nulls now
        plan = _make_plan(
            [_make_step(1, "handle_missing", "Fill Age", {"columns": "Age"})]
        )
        step_results = [_make_exec_result(1, "handle_missing")]
        vr = validate(original, result, plan, step_results, [])
        assert "POST_CLEAN_NULL_DROP" in vr.checks_failed

    def test_no_cleaning_steps_skips_null_check(self):
        original = _base_original_df()
        result = original.copy()
        plan = _make_plan([_make_step(1, "sort_values", "Sort", {"column": "Purchase"})])
        step_results = [_make_exec_result(1, "sort_values")]
        vr = validate(original, result, plan, step_results, [])
        assert "POST_CLEAN_NULL_DROP" in vr.checks_passed

    def test_failed_cleaning_step_skips_null_check(self):
        """If handle_missing failed (success=False), null check should skip."""
        original = _base_original_df()
        result = original.copy()
        result["Age"] = None  # nulls increased — but step failed
        plan = _make_plan(
            [_make_step(1, "handle_missing", "Fill Age", {"columns": "Age"})]
        )
        step_results = [_make_exec_result(1, "handle_missing", success=False)]
        vr = validate(original, result, plan, step_results, [])
        # No successful cleaning step ran, so check should be skipped (pass)
        assert "POST_CLEAN_NULL_DROP" in vr.checks_passed


# ---------------------------------------------------------------------------
# Check 4: REQUESTED_OUTPUT_EXISTS
# ---------------------------------------------------------------------------


class TestRequestedOutputExistsCheck:
    def test_derived_column_exists_passes(self):
        original = _base_original_df()
        result = original.copy()
        result["Revenue"] = result["Purchase"] * 1.1
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
        step_results = [_make_exec_result(1, "add_derived_column")]
        vr = validate(original, result, plan, step_results, [])
        assert "REQUESTED_OUTPUT_EXISTS" in vr.checks_passed

    def test_derived_column_missing_fails(self):
        original = _base_original_df()
        result = original.copy()  # 'Revenue' NOT added
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
        step_results = [_make_exec_result(1, "add_derived_column")]
        vr = validate(original, result, plan, step_results, [])
        assert "REQUESTED_OUTPUT_EXISTS" in vr.checks_failed

    def test_chart_step_with_no_chart_path_fails(self):
        original = _base_original_df()
        result = original.copy()
        plan = _make_plan(
            [
                _make_step(
                    1, "bar_chart", "Bar chart", {"x": "Name", "y": "Purchase"}
                )
            ]
        )
        step_results = [_make_exec_result(1, "bar_chart")]
        # chart_paths is empty — failure expected
        vr = validate(original, result, plan, step_results, chart_paths=[])
        assert "REQUESTED_OUTPUT_EXISTS" in vr.checks_failed

    def test_chart_step_with_chart_path_passes(self):
        original = _base_original_df()
        result = original.copy()
        plan = _make_plan(
            [
                _make_step(
                    1, "bar_chart", "Bar chart", {"x": "Name", "y": "Purchase"}
                )
            ]
        )
        step_results = [_make_exec_result(1, "bar_chart")]
        vr = validate(original, result, plan, step_results, chart_paths=["/tmp/bar_abc.png"])
        assert "REQUESTED_OUTPUT_EXISTS" in vr.checks_passed


# ---------------------------------------------------------------------------
# Retry metadata
# ---------------------------------------------------------------------------


class TestRetryMetadata:
    def test_can_retry_true_when_invalid_and_under_cap(self):
        original = _base_original_df()
        empty = pd.DataFrame(columns=original.columns)
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates")]
        vr = validate(original, empty, plan, step_results, [], retry_count=0, max_retries=2)
        assert vr.is_valid is False
        assert vr.can_retry is True

    def test_can_retry_false_when_at_cap(self):
        original = _base_original_df()
        empty = pd.DataFrame(columns=original.columns)
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates")]
        vr = validate(original, empty, plan, step_results, [], retry_count=2, max_retries=2)
        assert vr.can_retry is False

    def test_retry_count_stored_on_result(self):
        original = _base_original_df()
        result = original.copy()
        plan = _make_plan([_make_step(1, "drop_duplicates", "dedup")])
        step_results = [_make_exec_result(1, "drop_duplicates")]
        vr = validate(original, result, plan, step_results, [], retry_count=1, max_retries=3)
        assert vr.retry_count == 1
        assert vr.max_retries == 3


# ---------------------------------------------------------------------------
# Statelessness: same inputs → same output
# ---------------------------------------------------------------------------


class TestValidatorStatelessness:
    def test_same_inputs_produce_same_result(self):
        original = _base_original_df()
        result = original.dropna().reset_index(drop=True)
        plan = _make_plan([_make_step(1, "handle_missing", "fill", {"columns": "Age"})])
        step_results = [_make_exec_result(1, "handle_missing")]

        vr1 = validate(original, result, plan, step_results, [])
        vr2 = validate(original, result, plan, step_results, [])

        assert vr1.is_valid == vr2.is_valid
        assert vr1.checks_passed == vr2.checks_passed
        assert vr1.checks_failed == vr2.checks_failed
