"""Tests for backend/core/pipeline.py.

Verifies:
- Bounded retry loop runs AT MOST 3 times total (1 initial + 2 retries) under forced failure [FIX F2].
- LLM call budget hard limit stops the pipeline cleanly without hanging or crashing [FIX F9].
- Clarification short-circuit fires before execution when intent is ambiguous.
- Canonical pipeline end-to-end execution on sample.csv.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from backend.config import SESSIONS_DIR
from backend.core.exceptions import LLMBudgetExceededError
from backend.core.pipeline import (
    MAX_LLM_CALLS_PER_REQUEST,
    MAX_RETRIES,
    DataWisePipeline,
    LLMCallCounter,
)
from backend.models.schemas import PipelineStatus, ValidationResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample.csv"


@pytest.fixture
def tmp_sessions_dir(tmp_path: Path) -> Path:
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    return sessions


def _make_pipeline(sessions_dir: Path, **kwargs) -> DataWisePipeline:
    return DataWisePipeline(sessions_dir=sessions_dir, **kwargs)


class TestRetryLoopHardCap:
    """Verifies that the retry loop is bounded and hard-capped at 3 total attempts."""

    def test_loop_runs_at_most_3_times_under_forced_validation_failure(
        self, tmp_sessions_dir: Path
    ):
        """Prove the hard cap holds: 1 initial attempt + 2 retries = 3 total calls.

        Even if validate() is mocked to always return is_valid=False and can_retry=True,
        the pipeline must never exceed 3 attempts and must terminate cleanly.
        """
        pipeline = _make_pipeline(tmp_sessions_dir)

        # Mock validate to always report failure with can_retry=True
        mock_val = ValidationResult(
            is_valid=False,
            checks_passed=[],
            checks_failed=["ROW_COUNT_NONZERO"],
            details={"ROW_COUNT_NONZERO": "Forced test failure"},
            can_retry=True,
            retry_count=0,
            max_retries=2,
        )

        with patch("backend.processors.tabular.validate", return_value=mock_val) as mock_validate_fn:
            output = pipeline.run(
                uploaded_file=SAMPLE_CSV,
                original_filename="sample.csv",
                prompt="Clean this data",
            )

            # Assert the loop ran AT MOST 3 times total (1 initial + 2 retries)
            assert mock_validate_fn.call_count == 3, (
                f"Expected exactly 3 validation attempts, got {mock_validate_fn.call_count}"
            )
            assert pipeline.last_attempt_count == 3
            assert output.status == PipelineStatus.FAILED
            assert any("Validation failed after 3 attempt(s)" in e for e in output.errors)


class TestLLMBudgetEnforcement:
    """Verifies that LLMBudgetExceededError stops the pipeline cleanly under forced excess."""

    def test_counter_raises_when_cap_exceeded(self):
        counter = LLMCallCounter(max_calls=2)
        counter("call 1")
        counter("call 2")
        with pytest.raises(LLMBudgetExceededError, match="budget of 2 calls"):
            counter("call 3")

    def test_llm_budget_stops_pipeline_cleanly(self, tmp_sessions_dir: Path):
        """When an LLM client exceeds the budget cap, the pipeline halts gracefully."""
        dummy_llm = object()
        # Set max_llm_calls=1 so intent (call 1) succeeds but plan (call 2) hits the cap
        pipeline = DataWisePipeline(
            llm_client=dummy_llm,
            sessions_dir=tmp_sessions_dir,
            max_llm_calls=1,
        )

        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Clean this data and show me the top 10 by Purchase",
        )

        # Clean stop, no hang, no crash, structured FAILED status
        assert output.status == PipelineStatus.FAILED
        assert len(output.errors) > 0
        assert "LLM call budget of 1 calls per request exceeded" in output.errors[0]

    def test_llm_budget_exceeded_raises_when_raise_on_error(self, tmp_sessions_dir: Path):
        dummy_llm = object()
        pipeline = DataWisePipeline(
            llm_client=dummy_llm,
            sessions_dir=tmp_sessions_dir,
            max_llm_calls=1,
        )
        with pytest.raises(LLMBudgetExceededError):
            pipeline.run(
                uploaded_file=SAMPLE_CSV,
                original_filename="sample.csv",
                prompt="Clean this data",
                raise_on_error=True,
            )


class TestClarificationShortCircuit:
    """Verifies that ambiguous user intent triggers NEEDS_CLARIFICATION before execution."""

    def test_ambiguous_filter_prompt_short_circuits(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Filter the data",
        )
        assert output.status == PipelineStatus.NEEDS_CLARIFICATION
        assert "Which rows or condition should be filtered?" in output.summary
        assert output.total_rows == 50  # No rows removed; short-circuit before execution

    def test_ambiguous_calculate_prompt_short_circuits(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Calculate a new column",
        )
        assert output.status == PipelineStatus.NEEDS_CLARIFICATION
        assert "What calculation would you like to perform?" in output.summary


class TestPipelineEndToEnd:
    """Canonical end-to-end execution tests."""

    def test_clean_and_top10_produces_success(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Clean this data and show me the top 10 by Purchase",
        )
        assert output.status == PipelineStatus.SUCCESS
        assert output.total_rows == 10
        assert output.result_filename is not None
        assert output.download_url is not None
        assert len(output.preview_rows) == 10
        assert output.validation is not None
        assert output.validation.is_valid is True

    def test_clean_only_prompt(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Clean this data",
        )
        assert output.status == PipelineStatus.SUCCESS
        # sample.csv has 50 rows, 4 duplicates -> 46 cleaned rows
        assert output.total_rows == 46

    def test_result_file_exists_on_disk(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Clean this data",
        )
        assert output.result_file_path is not None
        assert Path(output.result_file_path).exists()

    def test_pipeline_exports_xlsx_format(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Clean this data",
            export_format="xlsx",
        )
        assert output.status == PipelineStatus.SUCCESS
        assert output.result_filename == "result.xlsx"
        assert Path(output.result_file_path).suffix == ".xlsx"

    def test_pipeline_exports_json_format(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=SAMPLE_CSV,
            original_filename="sample.csv",
            prompt="Clean this data",
            export_format="json",
        )
        assert output.status == PipelineStatus.SUCCESS
        assert output.result_filename == "result.json"
        assert Path(output.result_file_path).suffix == ".json"

    def test_empty_file_returns_failed(self, tmp_sessions_dir: Path):
        pipeline = _make_pipeline(tmp_sessions_dir)
        output = pipeline.run(
            uploaded_file=b"",
            original_filename="empty.csv",
            prompt="process",
        )
        assert output.status == PipelineStatus.FAILED
