"""Frontend utility and response-parsing helpers for DataWise.

Centralizes response parsing, security-focused error redaction, and UI formatting.
Ensures no internal file paths, stack traces, or raw JSON details leak to the UI.
"""

from __future__ import annotations

import re
from typing import Any

# Pattern matching Windows paths (e.g. C:\Users\...) and Unix absolute paths
_PATH_RE = re.compile(
    r"(?:[a-zA-Z]:[\\/][a-zA-Z0-9_.\-\\ /]+|/(?:home|usr|var|tmp|workspace)[a-zA-Z0-9_.\-/]+)",
    re.IGNORECASE,
)

# Pattern matching common stack trace indicators
_TRACE_RE = re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL)


def redact_sensitive_paths(text: str) -> str:
    """Redact internal filesystem paths and stack traces from error messages."""
    if not text:
        return ""
    # Remove any multiline traceback block first
    text = _TRACE_RE.sub("[internal error stack redacted]", text)
    # Redact filesystem paths
    return _PATH_RE.sub("[internal path]", text).strip()


def parse_error_response(
    resp_data: dict[str, Any] | None,
    default_msg: str = "An unexpected error occurred during processing.",
) -> dict[str, str]:
    """Extract error_code and sanitized message from backend error response.

    SECURITY/UX CONTRACT:
    - Displays ONLY error_code and plain-language message.
    - Omits the 'details' field entirely to prevent path / internal state leaks.
    - Strips any accidental filesystem paths or stack traces from the message.
    """
    if not resp_data or not isinstance(resp_data, dict):
        return {"error_code": "ERROR", "message": default_msg}

    code = str(resp_data.get("error_code") or "ERROR").strip()
    raw_msg = str(resp_data.get("message") or default_msg).strip()
    clean_msg = redact_sensitive_paths(raw_msg) or default_msg

    return {
        "error_code": code,
        "message": clean_msg,
    }


def extract_clarification_question(result_data: dict[str, Any]) -> str:
    """Extract a clean clarifying question from a NEEDS_CLARIFICATION response."""
    errors = result_data.get("errors", [])
    if errors and isinstance(errors, list) and len(errors) > 0:
        return str(errors[0])
    summary = str(result_data.get("summary", "")).strip()
    if summary:
        return summary
    return "Could you clarify your request with more specific details?"


def parse_pipeline_result(result_data: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and structure raw pipeline result dictionary for UI rendering."""
    if not result_data or not isinstance(result_data, dict):
        return {}
    return {
        "status": result_data.get("status", "unknown"),
        "session_id": result_data.get("session_id", ""),
        "summary": result_data.get("summary", ""),
        "preview_rows": result_data.get("preview_rows") or [],
        "preview_columns": result_data.get("preview_columns") or [],
        "total_rows": result_data.get("total_rows", 0),
        "executed_plan": result_data.get("executed_plan") or {},
        "validation": result_data.get("validation") or {},
        "chart_paths": result_data.get("chart_paths") or [],
        "result_filename": result_data.get("result_filename"),
        "errors": result_data.get("errors") or [],
        "batch_results": result_data.get("batch_results"),
        "batch_summary": result_data.get("batch_summary"),
    }
