# DataWise — Streamlit Frontend (Phase 7)

A modern, high-density web UI for the DataWise AI data agent.

---

## Prerequisites

1. Activate the Python virtual environment:
   ```powershell
   .venv\Scripts\Activate.ps1
   ```
2. Ensure the FastAPI backend is running:
   ```powershell
   .venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
   ```

---

## Running the Frontend

Start the Streamlit application:
```powershell
.venv\Scripts\streamlit.exe run frontend/app.py --server.port 8501
```

Once running, navigate to `http://localhost:8501` in your browser.

---

## Configuration

The frontend connects to the FastAPI backend via HTTP. You can configure the backend URL using the `DATAWISE_API_URL` environment variable:

```powershell
$env:DATAWISE_API_URL = "http://127.0.0.1:8000"
.venv\Scripts\streamlit.exe run frontend/app.py
```

Default: `http://127.0.0.1:8000`

---

## Features

- **File Upload**: Drag-and-drop support for `.csv`, `.xlsx`, and tabular `.json` up to 50 MB.
- **Natural-Language Instructions**: Free-text prompt box for data cleaning, transformation, aggregation, and charting instructions.
- **Export Format Selection**: Export outputs in CSV, Excel (`.xlsx`), or JSON.
- **Real-Time Pipeline Execution**: Direct REST integration with the backend pipeline (`POST /api/pipeline/run`).
- **Telemetry & Transparency**:
  - Top-level metrics: output rows, columns, execution steps, checks passed, checks failed.
  - Plain-English synthesis summary of all operations executed.
  - 5 interactive inspection tabs: **Preview**, **Charts**, **Execution Plan**, **Validation**, and **Downloads**.
- **Interactive Clarification**: Displays clarifying questions when instructions are ambiguous, with one-click resubmission.
- **Security & Error Redaction**: Strict error sanitization ensuring internal server filepaths, Python tracebacks, and raw JSON details are never surfaced to end users.
