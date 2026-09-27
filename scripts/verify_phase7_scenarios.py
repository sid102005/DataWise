"""Live verification script for Phase 7 scenarios."""

import sys

# Ensure UTF-8 printing on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from frontend.client import call_pipeline, fetch_file


def test_scenario_1_standard_flow():
    print("\n--- Scenario 1: Standard Success Flow ---")
    with open("tests/fixtures/sample.csv", "rb") as f:
        file_bytes = f.read()

    res, is_error = call_pipeline(
        file_bytes=file_bytes,
        filename="sample.csv",
        prompt="clean missing values, remove duplicates, and bar chart purchases by region",
        export_format="csv",
    )

    assert not is_error, f"Expected success but got error: {res}"
    assert res.get("status") in ("success", "partial_success"), f"Unexpected status: {res.get('status')}"
    session_id = res.get("session_id")
    assert session_id, "Missing session_id"

    # Verify plan
    plan = res.get("executed_plan", {})
    assert plan.get("steps"), "Missing execution plan steps"
    print(f"Plan steps count: {len(plan['steps'])}")

    # Verify preview table
    preview_rows = res.get("preview_rows", [])
    preview_cols = res.get("preview_columns", [])
    assert len(preview_rows) > 0, "Preview rows empty"
    assert len(preview_cols) > 0, "Preview columns empty"
    print(f"Preview table: {len(preview_rows)} rows x {len(preview_cols)} cols")

    # Verify chart paths
    chart_paths = res.get("chart_paths", [])
    print(f"Charts generated: {chart_paths}")
    assert len(chart_paths) > 0, "Expected at least 1 chart generated"

    # Verify summary
    summary = res.get("summary", "")
    assert summary, "Missing plain-English summary"
    print(f"Summary generated: {summary[:80]}...")

    # Verify file download
    result_filename = res.get("result_filename") or "result.csv"
    file_content = fetch_file(session_id, result_filename)
    assert file_content is not None, "Failed to download result file"
    assert len(file_content) > 0, "Downloaded file is empty"
    print(f"Downloaded result file: {len(file_content)} bytes")

    # Verify chart download
    chart_filename = chart_paths[0].replace("\\", "/").split("/")[-1]
    chart_content = fetch_file(session_id, chart_filename)
    assert chart_content is not None, "Failed to download chart PNG"
    assert len(chart_content) > 0, "Downloaded chart is empty"
    print(f"Downloaded chart file: {len(chart_content)} bytes")

    print("Scenario 1: PASS")
    return True


def test_scenario_2_malformed_file_flow():
    print("\n--- Scenario 2: Malformed File Error Flow ---")
    with open("tests/fixtures/malformed.csv", "rb") as f:
        file_bytes = f.read()

    res, is_error = call_pipeline(
        file_bytes=file_bytes,
        filename="malformed.csv",
        prompt="clean data",
        export_format="csv",
    )

    assert is_error, f"Expected error but got success: {res}"
    err_code = res.get("error_code")
    err_msg = res.get("message")
    print(f"Observed error_code: {err_code}")
    print(f"Observed message: {err_msg}")

    assert err_code == "FILE_VALIDATION_ERROR", f"Unexpected error code: {err_code}"
    assert err_msg, "Missing error message"

    # Security check: no raw stack trace or raw JSON
    assert "Traceback" not in err_msg, "Raw traceback leaked in error message"
    assert "{" not in err_msg, "Raw JSON leaked in error message"
    assert "details" not in res, "details field leaked to UI"
    print("Scenario 2: PASS")
    return True


def test_scenario_3_backend_down_flow():
    print("\n--- Scenario 3: Backend Down Flow ---")
    unreachable_url = "http://127.0.0.1:9999"

    res, is_error = call_pipeline(
        file_bytes=b"dummy,content\n1,2",
        filename="test.csv",
        prompt="clean",
        export_format="csv",
        api_base=unreachable_url,
    )

    assert is_error, "Expected error when backend is down"
    assert res.get("error_code") == "CONNECTION_ERROR", f"Unexpected error code: {res}"
    msg = res.get("message", "")
    print(f"Observed error_code: {res.get('error_code')}")
    print(f"Observed message: {msg}")
    assert "Could not reach the DataWise backend" in msg
    assert "Traceback" not in msg
    print("Scenario 3: PASS")
    return True


if __name__ == "__main__":
    ok1 = test_scenario_1_standard_flow()
    ok2 = test_scenario_2_malformed_file_flow()
    ok3 = test_scenario_3_backend_down_flow()
    if ok1 and ok2 and ok3:
        print("\n>>> ALL 3 SCENARIOS PASSED LIVE! <<<")
    else:
        sys.exit(1)
