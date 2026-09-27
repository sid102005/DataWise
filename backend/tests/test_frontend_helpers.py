"""Unit tests for frontend helper utilities, client, and response parsing (Phase 7)."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from frontend.client import call_pipeline, fetch_file
from frontend.helpers import (
    extract_clarification_question,
    parse_error_response,
    parse_pipeline_result,
    redact_sensitive_paths,
)


class TestErrorRedactionAndParsing:
    """Verify security contract that internal details and paths never leak to the UI."""

    def test_parse_error_response_file_validation_error(self):
        backend_response = {
            "error": True,
            "status": "error",
            "error_code": "FILE_VALIDATION_ERROR",
            "message": "File exceeds the 50MB size limit.",
            "details": "Internal path C:\\Users\\JOSEPH\\Desktop\\datawise\\workspace\\sessions\\xyz\\upload.csv",
        }
        parsed = parse_error_response(backend_response)
        assert parsed["error_code"] == "FILE_VALIDATION_ERROR"
        assert parsed["message"] == "File exceeds the 50MB size limit."
        # Confirm details field is completely omitted
        assert "details" not in parsed

    def test_parse_error_response_redacts_windows_path_in_message(self):
        raw_error = {
            "error_code": "PARSING_ERROR",
            "message": "Failed to read CSV at C:\\Users\\JOSEPH\\Desktop\\datawise\\temp\\file.csv: malformed header",
        }
        parsed = parse_error_response(raw_error)
        assert parsed["error_code"] == "PARSING_ERROR"
        assert "C:\\Users" not in parsed["message"]
        assert "[internal path]" in parsed["message"]

    def test_parse_error_response_redacts_unix_path_in_message(self):
        raw_error = {
            "error_code": "EXECUTION_ERROR",
            "message": "Permission denied reading /tmp/workspace/sessions/secret.csv",
        }
        parsed = parse_error_response(raw_error)
        assert "/tmp" not in parsed["message"]
        assert "[internal path]" in parsed["message"]

    def test_parse_error_response_redacts_traceback_block(self):
        raw_error = {
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": (
                "An unhandled error occurred.\n"
                "Traceback (most recent call last):\n"
                "  File 'c:/backend/main.py', line 45, in run\n"
                "    raise ValueError('secret db failure')"
            ),
        }
        parsed = parse_error_response(raw_error)
        assert "Traceback" not in parsed["message"]
        assert "secret db failure" not in parsed["message"]
        assert "[internal error stack redacted]" in parsed["message"]

    def test_parse_error_fallback_on_none_or_malformed(self):
        parsed = parse_error_response(None)
        assert parsed["error_code"] == "ERROR"
        assert "unexpected error" in parsed["message"].lower()

        parsed2 = parse_error_response({})
        assert parsed2["error_code"] == "ERROR"
        assert "unexpected error" in parsed2["message"].lower()


class TestClarificationExtraction:
    """Verify extraction of clarifying question for NEEDS_CLARIFICATION flows."""

    def test_extract_question_from_errors_list(self):
        payload = {
            "status": "needs_clarification",
            "errors": ["Did you mean sales in USD or EUR?"],
            "summary": "Ambiguous currency in prompt.",
        }
        question = extract_clarification_question(payload)
        assert question == "Did you mean sales in USD or EUR?"

    def test_extract_question_from_summary_fallback(self):
        payload = {
            "status": "needs_clarification",
            "errors": [],
            "summary": "Please specify the date range.",
        }
        question = extract_clarification_question(payload)
        assert question == "Please specify the date range."

    def test_extract_question_generic_fallback(self):
        payload = {"status": "needs_clarification"}
        question = extract_clarification_question(payload)
        assert "clarify" in question.lower()


class TestPipelineResultParsing:
    """Verify structuring of actual Phase 6 pipeline result shapes."""

    def test_parse_pipeline_result_success_shape(self):
        raw = {
            "status": "success",
            "session_id": "12345678-1234-4234-8234-123456789abc",
            "summary": "Cleaned missing values and generated bar chart.",
            "preview_rows": [{"A": 1, "B": 2}],
            "preview_columns": ["A", "B"],
            "total_rows": 50,
            "executed_plan": {
                "rationale": "Test rationale",
                "steps": [{"step_number": 1, "tool_name": "drop_duplicates"}],
            },
            "validation": {
                "is_valid": True,
                "checks_passed": ["ROW_COUNT_NONZERO"],
                "checks_failed": [],
            },
            "chart_paths": ["workspace/sessions/123/chart.png"],
            "result_filename": "result.csv",
        }
        res = parse_pipeline_result(raw)
        assert res["status"] == "success"
        assert res["session_id"] == "12345678-1234-4234-8234-123456789abc"
        assert len(res["preview_rows"]) == 1
        assert res["preview_columns"] == ["A", "B"]
        assert res["total_rows"] == 50
        assert len(res["executed_plan"]["steps"]) == 1
        assert res["result_filename"] == "result.csv"

    def test_parse_pipeline_result_empty(self):
        res = parse_pipeline_result(None)
        assert res == {}


class TestFrontendClient:
    """Verify HTTP client error interception, connection error, and timeout behavior."""

    @patch("frontend.client.requests.post")
    def test_call_pipeline_connection_error_no_traceback(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
        res, is_err = call_pipeline(
            file_bytes=b"dummy",
            filename="data.csv",
            prompt="clean",
            export_format="csv",
            api_base="http://127.0.0.1:8000",
        )
        assert is_err is True
        assert res["error_code"] == "CONNECTION_ERROR"
        assert "Could not reach the DataWise backend" in res["message"]
        assert "Traceback" not in res["message"]

    @patch("frontend.client.requests.post")
    def test_call_pipeline_timeout_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Read timed out")
        res, is_err = call_pipeline(
            file_bytes=b"dummy",
            filename="data.csv",
            prompt="clean",
            export_format="csv",
            api_base="http://127.0.0.1:8000",
        )
        assert is_err is True
        assert res["error_code"] == "TIMEOUT_ERROR"
        assert "timed out" in res["message"]

    @patch("frontend.client.requests.post")
    def test_call_pipeline_server_error_sanitization(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": True,
            "status": "error",
            "error_code": "FILE_VALIDATION_ERROR",
            "message": "File exceeds 50MB limit.",
            "details": "Server path: C:\\data\\secret_path\\test.csv",
        }
        mock_post.return_value = mock_resp

        res, is_err = call_pipeline(
            file_bytes=b"dummy",
            filename="data.csv",
            prompt="clean",
            export_format="csv",
            api_base="http://127.0.0.1:8000",
        )
        assert is_err is True
        assert res["error_code"] == "FILE_VALIDATION_ERROR"
        assert res["message"] == "File exceeds 50MB limit."
        assert "details" not in res

    @patch("frontend.client.requests.get")
    def test_fetch_file_success_and_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"csv,content\n1,2"
        mock_get.return_value = mock_resp

        content = fetch_file("sess-123", "result.csv", api_base="http://127.0.0.1:8000")
        assert content == b"csv,content\n1,2"

        mock_get.side_effect = Exception("network failure")
        assert fetch_file("sess-123", "result.csv", api_base="http://127.0.0.1:8000") is None
