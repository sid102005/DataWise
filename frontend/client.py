"""HTTP client for communicating with the DataWise backend API."""

from __future__ import annotations

import io
import os
from typing import Any

import requests

from frontend.helpers import (
    parse_error_response,
    parse_pipeline_result,
)

DEFAULT_API_BASE = "http://127.0.0.1:8000"


def get_api_base() -> str:
    """Return configured backend API base URL."""
    return os.environ.get("DATAWISE_API_URL", DEFAULT_API_BASE).rstrip("/")


def call_pipeline(
    file_bytes: bytes | None = None,
    filename: str | None = None,
    prompt: str = "",
    export_format: str = "csv",
    session_id: str | None = None,
    api_base: str | None = None,
    files_list: list[tuple[str, bytes]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Call the backend pipeline endpoint. Returns (result_dict, is_error).

    SECURITY/UX CONTRACT:
    - Never throws raw connection/timeout tracebacks to callers.
    - Errors are intercepted and returned as structured {error_code, message}.
    - Details field with internal paths or traces is completely omitted.
    """
    base = (api_base or get_api_base()).rstrip("/")

    if files_list and len(files_list) > 1:
        files = [("files", (fname, io.BytesIO(fbytes), "application/octet-stream")) for fname, fbytes in files_list]
    elif files_list and len(files_list) == 1:
        files = {"file": (files_list[0][0], io.BytesIO(files_list[0][1]), "application/octet-stream")}
    elif filename and file_bytes is not None:
        files = {"file": (filename, io.BytesIO(file_bytes), "application/octet-stream")}
    else:
        files = {}

    data: dict[str, Any] = {"prompt": prompt, "export_format": export_format}
    if session_id:
        data["session_id"] = session_id

    try:
        resp = requests.post(f"{base}/api/pipeline/run", files=files, data=data, timeout=120)
        try:
            payload = resp.json()
        except Exception:
            return {
                "error_code": "RESPONSE_PARSE_ERROR",
                "message": f"Server returned an invalid response (HTTP {resp.status_code}).",
            }, True

        if resp.status_code >= 400 or payload.get("error"):
            return parse_error_response(payload), True

        return parse_pipeline_result(payload), False

    except requests.exceptions.ConnectionError:
        return {
            "error_code": "CONNECTION_ERROR",
            "message": (
                f"Could not reach the DataWise backend at {base}. "
                "Please verify the backend server is running."
            ),
        }, True
    except requests.exceptions.Timeout:
        return {
            "error_code": "TIMEOUT_ERROR",
            "message": "The pipeline execution timed out after 120 seconds.",
        }, True
    except Exception as exc:
        return parse_error_response({"error_code": "CLIENT_ERROR", "message": str(exc)}), True


def fetch_file(session_id: str, filename: str, api_base: str | None = None) -> bytes | None:
    """Fetch an exported dataset or chart image from the backend."""
    base = (api_base or get_api_base()).rstrip("/")
    try:
        resp = requests.get(f"{base}/api/pipeline/download/{session_id}/{filename}", timeout=30)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def get_capabilities(api_base: str | None = None) -> dict[str, Any] | None:
    """Fetch live capabilities from the backend API. Returns None on connection failure."""
    base = (api_base or get_api_base()).rstrip("/")
    try:
        resp = requests.get(f"{base}/api/capabilities", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

