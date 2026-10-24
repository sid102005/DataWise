"""Unit and integration tests for DataWise LLM-backed structured planning layer.

Verifies:
- MockLLMProvider and LLMProvider base contracts.
- LLM structured intent parsing into validated Objective instances.
- LLM structured plan generation into validated Plan and Step sequences.
- Tool verification: rejection of unregistered tool names from LLM responses.
- Ambiguity detection: needs_clarification and clarification_question flags.
- Validation revision: LLM-backed plan revision incorporating validation.details.
- Resilient fallback: transparent degradation to deterministic heuristics on LLM error/timeout.
- Provider resolution: get_default_llm_provider with explicit arguments and env vars.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from backend.core.intent import parse_intent
from backend.core.llm_provider import (
    AnthropicProvider,
    GeminiProvider,
    LLMProvider,
    MockLLMProvider,
    OpenAIProvider,
    get_default_llm_provider,
)
from backend.core.planner import create_plan, revise_plan
from backend.models.schemas import (
    ColumnInfo,
    DataProfile,
    InferredType,
    Objective,
    ObjectiveCategory,
    Plan,
    Step,
    ValidationResult,
)


@pytest.fixture
def sample_profile() -> DataProfile:
    return DataProfile(
        file_format="csv",
        row_count=100,
        column_count=4,
        duplicate_row_count=5,
        columns=[
            ColumnInfo(
                name="id",
                raw_dtype="int64",
                inferred_type=InferredType.ID,
                null_count=0,
                null_percentage=0.0,
                unique_count=95,
            ),
            ColumnInfo(
                name="customer",
                raw_dtype="object",
                inferred_type=InferredType.TEXT,
                null_count=2,
                null_percentage=2.0,
                unique_count=80,
            ),
            ColumnInfo(
                name="revenue",
                raw_dtype="float64",
                inferred_type=InferredType.NUMERIC,
                null_count=1,
                null_percentage=1.0,
                unique_count=90,
            ),
            ColumnInfo(
                name="date",
                raw_dtype="object",
                inferred_type=InferredType.DATE,
                null_count=0,
                null_percentage=0.0,
                unique_count=50,
            ),
        ],
    )


class TestLLMProviderResolution:
    """Tests provider auto-detection and factory resolution."""

    def test_mock_provider_basics(self):
        mock = MockLLMProvider({"test": 123})
        res = mock.generate_structured("prompt", "system")
        assert res == {"test": 123}
        assert "Mock" in mock.get_provider_name()
        assert len(mock.calls) == 1

    def test_provider_resolution_none_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            prov = get_default_llm_provider()
            assert prov is None

    def test_provider_resolution_gemini(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key-gemini"}, clear=True):
            prov = get_default_llm_provider()
            assert isinstance(prov, GeminiProvider)
            assert prov.api_key == "test-key-gemini"

    def test_provider_resolution_anthropic(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-anthropic"}, clear=True):
            prov = get_default_llm_provider()
            assert isinstance(prov, AnthropicProvider)
            assert prov.api_key == "test-key-anthropic"

    def test_provider_resolution_openai(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key-openai"}, clear=True):
            prov = get_default_llm_provider()
            assert isinstance(prov, OpenAIProvider)
            assert prov.api_key == "test-key-openai"

    def test_provider_explicit_override(self):
        prov = get_default_llm_provider(explicit_key="custom-key", explicit_provider="gemini")
        assert isinstance(prov, GeminiProvider)
        assert prov.api_key == "custom-key"


class TestLLMIntentParsing:
    """Tests Stage 2 intent understanding using structured LLM output."""

    def test_llm_intent_parsing_success(self, sample_profile: DataProfile):
        mock = MockLLMProvider(
            {
                "objectives": [
                    {
                        "category": "clean",
                        "description": "Remove duplicates and handle missing values in revenue",
                        "target_columns": ["revenue"],
                        "parameters": {"strategy": "median"},
                    },
                    {
                        "category": "aggregate",
                        "description": "Rank top 10 customers by revenue",
                        "target_columns": ["customer", "revenue"],
                        "parameters": {"n": 10},
                    },
                ]
            }
        )

        objs = parse_intent("clean and rank top 10", sample_profile, llm_client=mock)
        assert len(objs) == 2
        assert objs[0].category == ObjectiveCategory.CLEAN
        assert objs[0].target_columns == ["revenue"]
        assert objs[1].category == ObjectiveCategory.AGGREGATE
        assert objs[1].parameters.get("n") == 10

    def test_llm_intent_fallback_on_error(self, sample_profile: DataProfile):
        """When LLM provider raises an exception, transparently fall back to deterministic parser."""
        class FailingProvider(LLMProvider):
            def generate_structured(self, *args, **kwargs):
                raise RuntimeError("API rate limit exceeded")

            def get_provider_name(self):
                return "Failing"

        failing_prov = FailingProvider()
        objs = parse_intent("clean data", sample_profile, llm_client=failing_prov)
        assert len(objs) >= 1
        assert objs[0].category == ObjectiveCategory.CLEAN


class TestLLMTaskPlanning:
    """Tests Stage 3 task planning and step synthesis using structured LLM output."""

    def test_llm_create_plan_success(self, sample_profile: DataProfile):
        mock = MockLLMProvider(
            {
                "rationale": "Clean dataset nulls and rank highest spending customers.",
                "needs_clarification": False,
                "clarification_question": None,
                "steps": [
                    {
                        "step_number": 1,
                        "tool_name": "drop_duplicates",
                        "description": "Remove duplicate entries",
                        "parameters": {"subset": ["id"]},
                        "expected_output": "Unique IDs only",
                    },
                    {
                        "step_number": 2,
                        "tool_name": "handle_missing",
                        "description": "Impute missing revenue using median",
                        "parameters": {"strategy": "fill_median", "columns": ["revenue"]},
                        "expected_output": "No null revenue entries",
                    },
                    {
                        "step_number": 3,
                        "tool_name": "top_n",
                        "description": "Filter top 5 highest revenues",
                        "parameters": {"by": "revenue", "n": 5},
                        "expected_output": "Top 5 rows",
                    },
                ],
            }
        )

        objectives = [
            Objective(category=ObjectiveCategory.CLEAN, description="Clean duplicates and nulls"),
            Objective(category=ObjectiveCategory.AGGREGATE, description="Top 5 revenue"),
        ]

        plan = create_plan(
            objectives=objectives,
            profile=sample_profile,
            session_id="test-session-123",
            llm_client=mock,
        )

        assert isinstance(plan, Plan)
        assert len(plan.steps) == 3
        assert plan.steps[0].tool_name == "drop_duplicates"
        assert plan.steps[1].tool_name == "handle_missing"
        assert plan.steps[2].tool_name == "top_n"
        assert plan.needs_clarification is False
        assert "Clean dataset" in plan.rationale

    def test_llm_plan_filters_unregistered_tools(self, sample_profile: DataProfile):
        """If LLM hallucinates an unregistered tool, it must be ignored for safety."""
        mock = MockLLMProvider(
            {
                "steps": [
                    {
                        "step_number": 1,
                        "tool_name": "hallucinated_arbitrary_code_exec",
                        "description": "Dangerous step",
                        "parameters": {},
                        "expected_output": "Bad state",
                    },
                    {
                        "step_number": 2,
                        "tool_name": "drop_duplicates",
                        "description": "Legitimate step",
                        "parameters": {},
                        "expected_output": "Good state",
                    },
                ]
            }
        )

        plan = create_plan(
            objectives=[Objective(category=ObjectiveCategory.CLEAN, description="Clean")],
            profile=sample_profile,
            session_id="test-session-123",
            llm_client=mock,
        )

        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "drop_duplicates"

    def test_llm_ambiguity_clarification(self, sample_profile: DataProfile):
        """When user prompt is contradictory, LLM can raise needs_clarification."""
        mock = MockLLMProvider(
            {
                "rationale": "Ambiguous request",
                "needs_clarification": True,
                "clarification_question": "Did you mean sort ascending or descending?",
                "steps": [],
            }
        )

        plan = create_plan(
            objectives=[Objective(category=ObjectiveCategory.TRANSFORM, description="Sort vaguely")],
            profile=sample_profile,
            session_id="test-session-123",
            llm_client=mock,
        )

        assert plan.needs_clarification is True
        assert plan.clarification_question == "Did you mean sort ascending or descending?"

    def test_llm_revise_plan_success(self, sample_profile: DataProfile):
        """Validation failure diagnostics guide the revised plan steps."""
        original_step = Step(
            step_number=1,
            tool_name="handle_missing",
            description="Drop nulls",
            parameters={"strategy": "drop"},
            expected_output="No nulls",
        )
        orig_plan = Plan(
            plan_id="orig-id",
            session_id="sess-id",
            objectives=[Objective(category=ObjectiveCategory.CLEAN, description="Clean")],
            steps=[original_step],
            rationale="Initial plan",
        )
        validation = ValidationResult(
            is_valid=False,
            checks_passed=[],
            checks_failed=["ROW_COUNT_NONZERO"],
            details={"ROW_COUNT_NONZERO": "Drop strategy eliminated all rows"},
            can_retry=True,
            retry_count=0,
            max_retries=2,
        )

        mock = MockLLMProvider(
            {
                "rationale": "Switching from drop to fill_median to preserve row count",
                "steps": [
                    {
                        "step_number": 1,
                        "tool_name": "handle_missing",
                        "description": "Fill nulls with median instead of dropping",
                        "parameters": {"strategy": "fill_median", "columns": ["revenue"]},
                        "expected_output": "Rows preserved",
                    }
                ],
            }
        )

        revised = revise_plan(
            original_plan=orig_plan,
            validation=validation,
            profile=sample_profile,
            llm_client=mock,
        )

        assert revised.revision_count == 1
        assert len(revised.steps) == 1
        assert revised.steps[0].parameters.get("strategy") == "fill_median"
        assert "median" in revised.rationale
