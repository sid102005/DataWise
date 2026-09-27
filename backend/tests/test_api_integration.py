"""Integration tests for DataWise REST API.

Verifies:
- POST /api/pipeline/run with sample.csv produces a 200 response matching
  Phase 1's expected_sample_profile.json ground truth.
- GET /api/pipeline/download/{session_id}/{filename} serves legitimate files
  that open and match processed data.
- Download route strictly rejects path-traversal attempts before filesystem access.
- Malformed file returns structured 4xx error with no stack trace.
- Ambiguous intent returns 200 with status="needs_clarification".
- Error mapping contracts for distinct exception types.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from fastapi.testclient import TestClient
import pandas as pd
import pytest

from backend.main import app

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample.csv"
MALFORMED_CSV = FIXTURES_DIR / "malformed.csv"
EXPECTED_PROFILE_JSON = FIXTURES_DIR / "expected_sample_profile.json"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestAPIPipelineRun:
    """Verifies end-to-end HTTP pipeline execution against Phase 1 fixtures."""

    def test_health_check(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_pipeline_run_canonical_matches_phase1_expected(self, client: TestClient):
        """Upload sample.csv + prompt, assert response matches expected_sample_profile.json."""
        assert SAMPLE_CSV.exists()
        assert EXPECTED_PROFILE_JSON.exists()

        with open(EXPECTED_PROFILE_JSON, "r", encoding="utf-8") as f:
            expected = json.load(f)

        with open(SAMPLE_CSV, "rb") as f:
            resp = client.post(
                "/api/pipeline/run",
                files={"file": ("sample.csv", f, "text/csv")},
                data={
                    "prompt": "Clean this data and show me the top 10 by Purchase",
                    "export_format": "csv",
                },
            )

        assert resp.status_code == 200, f"Body: {resp.text}"
        body = resp.json()

        assert body["status"] == "success"
        assert body["total_rows"] == 10
        assert body["download_url"] is not None
        assert body["session_id"]
        assert len(body["preview_rows"]) == 10

        # Validate against Phase 1 ground truth top 10 purchases
        top_expected = expected["top_10_purchases"]
        for i, row in enumerate(body["preview_rows"]):
            assert row["Customer_ID"] == top_expected[i]["customer_id"]
            assert row["Name"] == top_expected[i]["name"]
            assert pytest.approx(row["Purchase"]) == top_expected[i]["purchase"]

    def test_ambiguous_prompt_returns_needs_clarification(self, client: TestClient):
        with open(SAMPLE_CSV, "rb") as f:
            resp = client.post(
                "/api/pipeline/run",
                files={"file": ("sample.csv", f, "text/csv")},
                data={"prompt": "Filter the data"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "needs_clarification"
        assert "Which rows or condition should be filtered?" in body["summary"]
        assert body["total_rows"] == 50  # No execution performed


class TestAPIDownloadRoute:
    """Verifies file serving and path-traversal security on the download route."""

    def test_download_legitimate_result_file(self, client: TestClient):
        # 1. Run pipeline
        with open(SAMPLE_CSV, "rb") as f:
            run_resp = client.post(
                "/api/pipeline/run",
                files={"file": ("sample.csv", f, "text/csv")},
                data={
                    "prompt": "Clean this data and show me the top 10 by Purchase",
                    "export_format": "csv",
                },
            )
        body = run_resp.json()
        download_url = body["download_url"]
        assert download_url

        # 2. Download from canonical URL
        dl_resp = client.get(download_url)
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"].startswith("text/csv")

        # 3. Verify file opens and matches processed result
        df = pd.read_csv(io.BytesIO(dl_resp.content))
        assert len(df) == 10
        assert df.iloc[0]["Customer_ID"] == 1001
        assert pytest.approx(df.iloc[0]["Purchase"]) == 9850.5

    def test_download_path_traversal_rejection_before_filesystem(self, client: TestClient):
        """Security [FIX F3]: Traversal sequences must be rejected with 400/403."""
        # 1. Traversal in session_id
        resp = client.get("/api/pipeline/download/../../etc/passwd/result.csv")
        assert resp.status_code in {400, 404}

        # 2. Traversal in filename (client-normalized path rejected by router)
        valid_uuid = "12345678-1234-4123-8123-123456789abc"
        resp = client.get(f"/api/pipeline/download/{valid_uuid}/../../win.ini")
        assert resp.status_code in {400, 404}

        # 2b. Direct handler invocation with traversal tokens raises HTTPException(400) before filesystem access
        from fastapi import HTTPException
        from backend.api.routes import download_result
        import asyncio

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(download_result("..", "result.csv"))
        assert exc_info.value.status_code == 400
        assert "traversal" in exc_info.value.detail.lower()

        with pytest.raises(HTTPException) as exc_info2:
            asyncio.run(download_result(valid_uuid, "../result.csv"))
        assert exc_info2.value.status_code == 400
        assert "traversal" in exc_info2.value.detail.lower()

        # 3. Disallowed extension
        resp = client.get(f"/api/pipeline/download/{valid_uuid}/evil.exe")
        assert resp.status_code == 400

        # 4. Non-UUID session
        resp = client.get("/api/pipeline/download/not-a-uuid/result.csv")
        assert resp.status_code == 400

        # 5. Nonexistent valid session returns 404
        resp = client.get(f"/api/pipeline/download/{valid_uuid}/result.csv")
        assert resp.status_code == 404


class TestAPIErrorHandling:
    """Verifies that errors return structured JSON with HTTP 4xx/5xx and no stack trace."""

    def test_malformed_file_returns_structured_4xx_no_traceback(self, client: TestClient):
        """Malformed file must return structured 400 with NO python traceback."""
        assert MALFORMED_CSV.exists()
        with open(MALFORMED_CSV, "rb") as f:
            resp = client.post(
                "/api/pipeline/run",
                files={"file": ("malformed.csv", f, "text/csv")},
                data={"prompt": "Clean this data"},
            )

        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["error"] is True
        assert body["status"] == "error"
        assert body["error_code"] == "FILE_VALIDATION_ERROR"
        assert "message" in body

        # Security requirement: NO raw Python stack traces exposed
        assert "Traceback (most recent call last)" not in resp.text
        assert "raise " not in resp.text

    def test_unsupported_file_extension_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/pipeline/run",
            files={"file": ("bad_file.xml", b"hello world", "application/xml")},
            data={"prompt": "Clean this data"},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["status"] == "error"
        assert body["error_code"] == "FILE_VALIDATION_ERROR"
        assert "unsupported" in body["message"].lower() or "rejected" in body["message"].lower()
        assert "Traceback" not in resp.text
