"""Phase 8 End-to-End Functional Scenarios.

Exercises three distinct pipeline scenarios with hand-computed expected values:
1. Transform-only prompt (no cleaning)
2. Chart-only prompt (preserves all rows, outputs chart PNG)
3. Ambiguous prompt -> NEEDS_CLARIFICATION -> resubmission with clarification -> SUCCESS
"""

import pathlib
import pytest
import requests
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.schemas import PipelineStatus


@pytest.fixture(scope="module")
def sample_csv_bytes() -> bytes:
    path = pathlib.Path("tests/fixtures/sample.csv")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def api_client():
    with TestClient(app) as client:
        yield client


class TestE2EScenarios:
    """Three comprehensive functional end-to-end scenarios."""

    def test_scenario_1_transform_only_no_cleaning(self, api_client, sample_csv_bytes):
        """Scenario 1: Transform-only prompt without cleaning.

        Hand-computed ground truth on tests/fixtures/sample.csv:
        - Total original rows: 50
        - Region == 'East' rows: exactly 11 rows
        - Expected: Exactly 1 step (filter_rows), 0 clean steps, result rows = 11.
        """
        response = api_client.post(
            "/api/pipeline/run",
            files={"file": ("sample.csv", sample_csv_bytes, "text/csv")},
            data={"prompt": "filter rows where Region == East", "export_format": "csv"},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["status"] == "success"
        session_id = data["session_id"]
        assert session_id

        # Verify plan: only filter_rows step, NO clean steps
        plan = data["executed_plan"]
        assert plan is not None
        step_names = [s["tool_name"] for s in plan["steps"]]
        assert "filter_rows" in step_names
        assert "drop_duplicates" not in step_names
        assert "handle_missing" not in step_names
        assert "standardize_dates" not in step_names

        # Verify hand-computed row count: exactly 11
        assert data["total_rows"] == 11
        preview_rows = data["preview_rows"]
        assert len(preview_rows) == 11
        for row in preview_rows:
            assert row["Region"] == "East"

        # Verify download
        dl_resp = api_client.get(f"/api/pipeline/download/{session_id}/result.csv")
        assert dl_resp.status_code == 200
        assert len(dl_resp.content) > 0

    def test_scenario_2_chart_only_prompt(self, api_client, sample_csv_bytes):
        """Scenario 2: Chart-only prompt.

        Prompt requests only visualization.
        Expected:
        - bar_chart step executed
        - 0 clean steps
        - All 50 original rows preserved
        - Generated PNG chart exists and is downloadable
        """
        response = api_client.post(
            "/api/pipeline/run",
            files={"file": ("sample.csv", sample_csv_bytes, "text/csv")},
            data={"prompt": "generate a bar chart of Purchase by Region", "export_format": "csv"},
        )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["status"] == "success"
        session_id = data["session_id"]
        assert session_id

        # Verify plan: contains bar_chart, no clean steps
        plan = data["executed_plan"]
        step_names = [s["tool_name"] for s in plan["steps"]]
        assert "bar_chart" in step_names
        assert "drop_duplicates" not in step_names
        assert "handle_missing" not in step_names

        # Row count preserved: 50 rows
        assert data["total_rows"] == 50

        # Verify chart was generated
        chart_paths = data.get("chart_paths") or []
        assert len(chart_paths) >= 1
        chart_filename = chart_paths[0].replace("\\", "/").split("/")[-1]

        # Verify chart download via API
        chart_resp = api_client.get(f"/api/pipeline/download/{session_id}/{chart_filename}")
        assert chart_resp.status_code == 200
        assert chart_resp.headers["content-type"] == "image/png"
        assert len(chart_resp.content) > 1000

    def test_scenario_3_ambiguous_clarification_resubmission(self, api_client, sample_csv_bytes):
        """Scenario 3: Ambiguous case -> NEEDS_CLARIFICATION -> resubmission -> SUCCESS.

        Step A: Prompt is 'filter rows' (underspecified condition).
        Expected: Status is NEEDS_CLARIFICATION, 50 rows preserved, no execution steps.

        Step B: Resubmit with same session and clarified prompt 'filter rows where Region == East'.
        Expected: Status is success, result rows = 11.
        """
        # Step A: Ambiguous request
        resp_a = api_client.post(
            "/api/pipeline/run",
            files={"file": ("sample.csv", sample_csv_bytes, "text/csv")},
            data={"prompt": "filter rows", "export_format": "csv"},
        )
        assert resp_a.status_code == 200, resp_a.text
        data_a = resp_a.json()

        assert data_a["status"] == "needs_clarification"
        session_id = data_a["session_id"]
        assert session_id
        assert "Which rows or condition should be filtered?" in data_a["summary"]
        assert data_a["total_rows"] == 50
        assert len(data_a.get("execution_results") or []) == 0

        # Step B: Resubmission with clarification
        resp_b = api_client.post(
            "/api/pipeline/run",
            files={"file": ("sample.csv", sample_csv_bytes, "text/csv")},
            data={
                "prompt": "filter rows where Region == East",
                "session_id": session_id,
                "export_format": "csv",
            },
        )
        assert resp_b.status_code == 200, resp_b.text
        data_b = resp_b.json()

        assert data_b["status"] == "success"
        assert data_b["session_id"] == session_id
        assert data_b["total_rows"] == 11
        assert len(data_b["preview_rows"]) == 11
        for row in data_b["preview_rows"]:
            assert row["Region"] == "East"
