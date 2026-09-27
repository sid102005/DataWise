"""Unit tests for DataWise Pydantic data models in backend/models/schemas.py.

Verifies valid and invalid schema instantiations for every core data contract.
"""

import pytest
from pydantic import ValidationError

from backend.models.schemas import (
    InferredType,
    ObjectiveCategory,
    PipelineStatus,
    ColumnInfo,
    DataProfile,
    Objective,
    Step,
    Plan,
    ExecutionResult,
    ValidationResult,
    PipelineOutput,
    ErrorResponse,
    ClarificationRequest,
)


class TestColumnInfo:
    def test_valid(self):
        col = ColumnInfo(
            name="Age",
            inferred_type=InferredType.NUMERIC,
            raw_dtype="int64",
            null_count=6,
            null_percentage=12.0,
            unique_count=31,
            quality_issues=["Missing values detected"],
        )
        assert col.name == "Age"
        assert col.null_count == 6

    def test_invalid_negative_null_count(self):
        with pytest.raises(ValidationError):
            ColumnInfo(
                name="Age",
                inferred_type=InferredType.NUMERIC,
                raw_dtype="int64",
                null_count=-1,  # Must be >= 0
                null_percentage=0.0,
                unique_count=10,
            )

    def test_invalid_extra_field(self):
        with pytest.raises(ValidationError):
            ColumnInfo(
                name="Age",
                inferred_type=InferredType.NUMERIC,
                raw_dtype="int64",
                null_count=0,
                null_percentage=0.0,
                unique_count=10,
                forbidden_extra="bad",  # extra="forbid"
            )


class TestDataProfile:
    def test_valid(self):
        col = ColumnInfo(
            name="ID",
            inferred_type=InferredType.ID,
            raw_dtype="int64",
            null_count=0,
            null_percentage=0.0,
            unique_count=50,
        )
        profile = DataProfile(
            file_format="csv",
            encoding="utf-8",
            row_count=50,
            column_count=1,
            duplicate_row_count=4,
            duplicate_percentage=8.0,
            columns=[col],
            quality_flags=["4 duplicate rows found"],
        )
        assert profile.row_count == 50
        assert profile.file_format == "csv"

    def test_invalid_format(self):
        col = ColumnInfo(
            name="ID",
            inferred_type=InferredType.ID,
            raw_dtype="int64",
            null_count=0,
            null_percentage=0.0,
            unique_count=50,
        )
        with pytest.raises(ValidationError):
            DataProfile(
                file_format="doc",  # Not in Literal
                row_count=50,
                column_count=1,
                duplicate_row_count=0,
                duplicate_percentage=0.0,
                columns=[col],
            )

    def test_tabular_guarantees(self):
        # CSV with missing row_count/column_count should fail
        with pytest.raises(ValidationError) as exc:
            DataProfile(
                file_format="csv",
                row_count=None,
                column_count=None
            )
        assert "Tabular profiles must have non-null row_count and column_count" in str(exc.value)

        # PDF with missing row_count/column_count should pass
        doc_profile = DataProfile(
            file_format="pdf",
            row_count=None,
            column_count=None
        )
        assert doc_profile.file_format == "pdf"


class TestObjective:
    def test_valid(self):
        obj = Objective(
            category=ObjectiveCategory.CLEAN,
            description="Remove duplicate rows and impute missing Age",
            target_columns=["Age"],
            parameters={"strategy": "median"},
        )
        assert obj.category == ObjectiveCategory.CLEAN

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            Objective(
                category="invalid_category",  # not in ObjectiveCategory
                description="Invalid operation",
            )


class TestStep:
    def test_valid(self):
        step = Step(
            step_number=1,
            tool_name="drop_duplicates",
            description="Drop fully identical rows",
            parameters={"subset": None},
            expected_output="Dataset has zero duplicate rows",
        )
        assert step.step_number == 1
        assert step.tool_name == "drop_duplicates"

    def test_invalid_step_number(self):
        with pytest.raises(ValidationError):
            Step(
                step_number=0,  # ge=1 required
                tool_name="drop_duplicates",
                description="Zero step",
                expected_output="Invalid",
            )


class TestPlan:
    def test_valid(self):
        step = Step(
            step_number=1,
            tool_name="drop_duplicates",
            description="Drop duplicate rows",
            expected_output="Duplicates removed",
        )
        obj = Objective(
            category=ObjectiveCategory.CLEAN,
            description="Clean data",
        )
        plan = Plan(
            plan_id="plan-123",
            session_id="sess-abc",
            objectives=[obj],
            steps=[step],
            rationale="Initial cleaning pass",
        )
        assert plan.plan_id == "plan-123"
        assert len(plan.steps) == 1

    def test_invalid_missing_required(self):
        with pytest.raises(ValidationError):
            Plan(
                plan_id="plan-123",
                # missing session_id, objectives, steps
            )


class TestExecutionResult:
    def test_valid(self):
        res = ExecutionResult(
            step_number=1,
            tool_name="drop_duplicates",
            success=True,
            rows_before=50,
            rows_after=46,
            columns_before=6,
            columns_after=6,
            summary="Removed 4 duplicate rows",
            execution_time_ms=12.5,
        )
        assert res.success is True
        assert res.rows_after == 46

    def test_invalid_negative_rows(self):
        with pytest.raises(ValidationError):
            ExecutionResult(
                step_number=1,
                tool_name="drop_duplicates",
                success=True,
                rows_before=-5,  # ge=0 required
                rows_after=46,
                columns_before=6,
                columns_after=6,
                summary="Bad rows",
            )


class TestValidationResult:
    def test_valid(self):
        val = ValidationResult(
            is_valid=True,
            checks_passed=["row_count_sanity", "null_reduction"],
            checks_failed=[],
            details={"row_count_sanity": "Maintained 46 rows"},
            can_retry=False,
            retry_count=0,
            max_retries=2,
        )
        assert val.is_valid is True

    def test_invalid_max_retries(self):
        with pytest.raises(ValidationError):
            ValidationResult(
                is_valid=False,
                max_retries=0,  # ge=1 required
            )


class TestPipelineOutput:
    def test_valid(self):
        out = PipelineOutput(
            session_id="sess-xyz",
            status=PipelineStatus.SUCCESS,
            summary="Cleaned 50 rows, removed 4 duplicates, returned top 10.",
            total_rows=10,
            preview_columns=["Customer_ID", "Purchase"],
            preview_rows=[{"Customer_ID": 1001, "Purchase": 9850.5}],
        )
        assert out.status == PipelineStatus.SUCCESS
        assert len(out.preview_rows) == 1

    def test_invalid_negative_total_rows(self):
        with pytest.raises(ValidationError):
            PipelineOutput(
                session_id="sess-xyz",
                status=PipelineStatus.SUCCESS,
                summary="Cleaned data",
                total_rows=-1,  # ge=0 required
            )


class TestErrorResponse:
    def test_valid(self):
        err = ErrorResponse(
            error_code="UNSUPPORTED_FORMAT",
            message="Only CSV, XLSX, and JSON files are currently supported.",
            details="Provided file had extension .txt",
        )
        assert err.error is True
        assert err.error_code == "UNSUPPORTED_FORMAT"

    def test_invalid_missing_code(self):
        with pytest.raises(ValidationError):
            ErrorResponse(
                message="Missing error_code",
            )


class TestClarificationRequest:
    def test_valid(self):
        req = ClarificationRequest(
            session_id="sess-clarify-1",
            question="Column Date has mixed formats. Which format should be standardized?",
            context="Detected 33 rows with YYYY-MM-DD and 17 rows with DD/MM/YYYY.",
            options=["YYYY-MM-DD (ISO)", "DD/MM/YYYY"],
            default_choice="YYYY-MM-DD (ISO)",
            affected_column="Date",
        )
        assert req.affected_column == "Date"
        assert len(req.options) == 2

    def test_invalid_missing_question(self):
        with pytest.raises(ValidationError):
            ClarificationRequest(
                session_id="sess-clarify-1",
                context="Missing question",
            )
