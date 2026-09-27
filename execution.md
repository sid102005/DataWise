# DataWise — Codebase Execution & Runtime Flow (execution.md)

This document describes the actual runtime execution of the DataWise codebase, tracking the entry point, call chains, module interactions, branching logic, error handling, and verified feature implementation status.

---

## 1. Current Codebase State Overview

Following completion of Phase 1 (Skeleton & Canonical Contracts):
- **Core Specifications:** [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md), [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md), [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md), [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)
- **Technical Decisions:** [decision.md](file:///c:/Users/JOSEPH/Desktop/datawise/decision.md) (7 recorded decisions, including single-worker constraints, metadata-only LLM privacy boundaries, and fixture specifications)
- **Runtime Environment:** Python 3.14.7 virtual environment (`.venv/`) initialized with all pinned dependencies frozen in [requirements.txt](file:///c:/Users/JOSEPH/Desktop/datawise/requirements.txt)
- **Core Data Contracts:** Implemented in [backend/models/schemas.py](file:///c:/Users/JOSEPH/Desktop/datawise/backend/models/schemas.py) (`ColumnInfo`, `DataProfile`, `Objective`, `Step`, `Plan`, `ExecutionResult`, `ValidationResult`, `PipelineOutput`, `ErrorResponse`, `ClarificationRequest`)
- **API Entry Point:** [backend/main.py](file:///c:/Users/JOSEPH/Desktop/datawise/backend/main.py) implemented with `/health` route, lifespan workspace initialization, and single-worker (`workers=1`) constraint enforcement
- **Workspace Directories:** `workspace/sessions/` auto-created on application startup via `backend.config:ensure_workspace_directories()`
- **Canonical Test Fixtures:** Established in `tests/fixtures/` with hand-computed ground truth in `expected_sample_profile.json` and documented in `README.md`:
  - `sample.csv`, `sample.xlsx`, `sample.json` (50 rows, 6 columns, 4 duplicates, 6 null Ages, mixed Date formats, strictly unambiguous top 10 Purchases)
  - `malformed.csv` (structural error testing)
  - `oversized_placeholder.txt` (extension rejection testing)
  - `path_traversal_attempt.csv` (Phase 2 upload filename security testing)
- **Automated Tests:** 24 unit tests in [backend/tests/test_schemas.py](file:///c:/Users/JOSEPH/Desktop/datawise/backend/tests/test_schemas.py) and [backend/tests/test_health.py](file:///c:/Users/JOSEPH/Desktop/datawise/backend/tests/test_health.py) fully passing.


---

## 2. Application Entry Point

### Target Entry File & Server
- **Backend Entry File:** `backend/main.py`
- **Backend Entry Function:** `create_app()` / `main()`
- **Backend Start Command:** `.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1`
- **Frontend Entry File:** `frontend/app.py`
- **Frontend Start Command:** `.venv\Scripts\streamlit.exe run frontend/app.py --server.port 8501`
- **Frontend URL:** `http://localhost:8501`

### Execution Chain on Startup
```text
Application Start
        ↓
uvicorn.run("backend.main:app", workers=1)
        ↓
backend.main:create_app()
        ↓
configure_cors_and_middleware()
        ↓
ensure_workspace_directories()  # creates workspace/sessions/ on startup
        ↓
FastAPI server ready for HTTP requests
```

---

## 3. Function-to-Function Execution Architecture

```text
Frontend Startup / Render [frontend/app.py]
 └── get_capabilities() [frontend/client.py]
      └── GET /api/capabilities [backend/api/routes.py]
           └── ProcessorRegistry + capabilities.json + CATEGORY_EXTENSIONS
           └── Returns live supported extensions & categories (or safe fallback ['csv','xlsx','json'])
      └── Configures st.file_uploader(type=supported_types) & sidebar format pills dynamically

User interaction: Upload file + prompt + Run [frontend/app.py]
 └── call_pipeline() [frontend/client.py]
      └── POST /api/pipeline/run [backend/api/routes.py]
           └── DataWisePipeline.run() [backend/core/pipeline.py]
                ├── Stage 1: InputManager.validate_and_save() [backend/core/input_manager.py]
                │    ├── Determine original filename & validate extension (.csv, .xlsx, .json)
                │    ├── Enforce 50MB file size limit
                │    ├── Create isolated session folder: workspace/sessions/{session_id}/
                │    ├── SECURITY [FIX F3]: Save strictly as input{ext} (ignoring original filename for paths)
                │    ├── Record display metadata in workspace/sessions/{session_id}/metadata.json
                │    └── SECURITY [FIX F4]: Inspect Excel decompressed cell count <= 5,000,000 cells via openpyxl
                ├── Stage 2: DataUnderstanding.profile_data() [backend/core/understanding.py]
                │    ├── detect_format_and_encoding() [utf-8 chunk test with latin-1 fallback for CSV]
                │    ├── parse_dataframe() [loads pd.DataFrame, discovers workbook sheet names for .xlsx]
                │    ├── infer_column_types() [inferred_type: id, date, numeric, categorical, text]
                │    └── calculate_quality_metrics() [null counts, duplicate rows, quality_flags] -> DataProfile
                ├── Stage 3: IntentUnderstanding.parse_intent() [backend/core/intent.py]
                ├── Stage 4: TaskPlanner.create_plan() [backend/core/planner.py]
                ├── Stage 5: ExecutionLayer.execute_plan() [backend/core/executor.py]
                ├── Stage 6: ValidationLayer.validate() [backend/core/validator.py]
                └── Stage 7: OutputGenerator.generate() [backend/core/output.py]
 └── Response Sanitization & Parsing [frontend/helpers.py:parse_pipeline_result / parse_error_response]
 └── UI Rendering [frontend/app.py]
      ├── Status badges & telemetry metric grid (category-adapted: tabular, document, image)
      ├── Tab 1: Preview (tabular: pd.DataFrame; document: text area + word count; image: inline st.image + dimensions)
      ├── Tab 2: Charts (fetch_file() -> inline st.image)
      ├── Tab 3: Execution Plan (objectives, step cards, timing telemetry)
      ├── Tab 4: Validation (checks passed/failed, retry audit)
      └── Tab 5: Downloads (fetch_file() -> st.download_button for CSV/XLSX/JSON/PNG)
```

---

## 4. File-to-File Module Interaction

```text
frontend/app.py
       ↓
frontend/client.py
       ↓ (HTTP REST: GET /api/capabilities, POST /api/pipeline/run, GET /api/pipeline/download/{session_id}/{filename})
backend/main.py
       ↓
backend/api/routes.py
       ↓
backend/core/pipeline.py
 ├── backend/core/input_manager.py (validated save, fixed internal filename, xlsx decompression bomb guard)
 ├── backend/core/understanding.py (format/encoding detection, parser, type inference, DataProfile)
 ├── backend/core/intent.py
 ├── backend/core/planner.py
 ├── backend/core/executor.py -> backend/tools/ (clean.py, transform.py, aggregate.py, chart.py)
 ├── backend/core/validator.py
 └── backend/core/output.py
       ↓ (JSON Response: PipelineOutput or ErrorResponse)
frontend/helpers.py (error redaction, regex path scrubbing, result normalization)
       ↓
frontend/app.py (Streamlit UI display)
```

---

## 5. Detailed Request Execution Cycle

For a standard request:
```text
HTTP POST /api/pipeline/run
(Multipart: file + prompt + optional session_id)
        ↓
[INPUT VALIDATION & SECURITY STORAGE]
1. InputManager.validate_and_save()
   - Extension allow-list verification (.csv, .xlsx, .json)
   - Size limit enforcement (<= 50MB on-disk)
   - Generate session_id (UUID4) and mkdir workspace/sessions/{session_id}/
   - Fixed Internal Filename: Save strictly to workspace/sessions/{session_id}/input{ext}
   - Assert resolved path is inside session folder (blocks path traversal ../../../evil.csv)
   - If Excel: openpyxl read_only inspects sum(sheet.max_row * sheet.max_col) <= 5,000,000 cells
   - Persist metadata.json with display filename and size
        ↓
[FILE DETECTION & PROCESSOR ROUTING (Phase 9)]
2. detect_file() + get_processor()
   - Sniff magic bytes (PK, %PDF, etc.)
   - If magic bytes disagree with extension, magic bytes win (except for zip-based formats)
   - Route to TabularProcessor for tabular files (documents/images via other processors in future phases)
        ↓
[DATA UNDERSTANDING & PROFILING]
3. processor.profile() -> DataUnderstanding.profile_data()
   - detect_format_and_encoding(): UTF-8 test with latin-1 fallback
   - parse_dataframe(): CSV / openpyxl first-sheet / JSON parser
   - infer_column_types(): ID, Date, Numeric, Categorical, Text
   - calculate_quality_metrics(): Duplicate row count, null counts, quality flags
   - Emit populated metadata-only DataProfile Pydantic object
        ↓
[INTENT UNDERSTANDING (Stage 2)]
        ↓
[TASK PLANNING (Stage 3)]
        ↓
[TASK EXECUTION (Stage 4)]
        ↓
[VALIDATION (Stage 5)]
        ↓
[OUTPUT GENERATION (Stage 6)]
        ↓
HTTP 200 JSON Response
```

---

## 6. Branching and Conditional Execution Flow

1. **File Format & Security Branching:**
   - **Extension Check:** Suffix not in `{'.csv', '.xlsx', '.json'}` -> raise `FileValidationError`.
   - **Size Check:** File bytes > 50MB -> raise `FileValidationError`.
   - **Path Traversal Check:** Original upload filename never used in path; target strictly `session_dir / input{ext}`.
   - **Excel Decompression Bomb Check:** Total cells across sheets > 5,000,000 -> unlink file and raise `FileValidationError`.
   - **CSV Parsing:** Decodes with UTF-8; if `UnicodeDecodeError` triggers, falls back to `latin-1`. Parser errors trigger `FileValidationError`.
   - **Excel Parsing:** Discovers all sheet names via `openpyxl`; reads primary sheet via `pandas.read_excel`.
   - **JSON Parsing:** Parses tabular record lists; structural errors trigger `FileValidationError`.

2. **Clarification vs Proceed Branching:**
   - If user instruction is ambiguous (e.g. "Filter the data" or "Calculate" without condition/columns):
     - `planner.check_ambiguity_and_clarification()` detects underspecified intent and emits a `ClarificationRequest`.
     - The pipeline short-circuits immediately before Stage 4 execution, returning HTTP 200 with status `NEEDS_CLARIFICATION`, row count untouched, and targeted question in summary/errors.
   - If a sensible default exists (e.g. median for numeric imputation, ISO format for dates):
     - Proceed, noting the assumption explicitly in the summary.

3. **Validation Failure & Bounded Auto-Retry Branching [FIX F2]:**
   - Implemented as an explicit bounded `for attempt in range(MAX_RETRIES + 1)` loop strictly inside `pipeline.py`.
   - Max 3 total attempts (1 initial attempt + 2 retries). Tested under forced validation failure.
   - If validation fails and attempt < 2: `planner.revise_plan()` generates a revised plan and re-executes.
   - If attempt == 2 or validation says `can_retry=False`: loop terminates, returning `PipelineOutput` with `FAILED` or `PARTIAL_SUCCESS` and a plain-language explanation. Neither `executor.py` nor `validator.py` contain any retry orchestration.

4. **LLM Call Budget Enforcement [FIX F9]:**
   - Single `LLMCallCounter` shared across the pipeline request (`MAX_LLM_CALLS_PER_REQUEST = 6`).
   - Every invocation of `intent.parse_intent()`, `planner.build_plan()`, and `planner.revise_plan()` increments this counter.
   - If exceeded, raises `LLMBudgetExceededError`, which halts the pipeline cleanly, returning structured error status without hanging or crash.

5. **Path-Safe Download Security Contract [FIX F3]:**
   - `GET /api/pipeline/download/{session_id}/{filename}` (and alias `/api/download/{session_id}/{filename}`).
   - Pre-filesystem validation: rejects any session_id or filename containing `..`, `/`, or `\\` with HTTP 400.
   - UUID4 regex validation: rejects non-UUID session IDs with HTTP 400.
   - Allow-list filename check: strictly matches `result.(csv|xlsx|json)` or `*.png`.
   - Confinement check: `target_path.is_relative_to(session_dir)` and `is_relative_to(SESSIONS_DIR)` ensures zero directory traversal.

---

## 7. Error Execution Flow

```text
Exception or Constraint Violation
        ↓
Specific Exception Type Caught:
  - FileValidationError   → HTTP 400 (FILE_VALIDATION_ERROR)
  - ToolInputError        → HTTP 400 (TOOL_INPUT_ERROR)
  - LLMBudgetExceededError→ HTTP 429 (LLM_BUDGET_EXCEEDED)
  - ExecutionError        → HTTP 500 (EXECUTION_ERROR)
  - DataWiseValidationError→HTTP 422 (VALIDATION_ERROR)
        ↓
Server-side logging (log.warning / log.exception)
        ↓
Sanitized JSON Response (zero raw Python tracebacks surfaced to user):
{
  "error": true,
  "status": "error",
  "error_code": "FILE_VALIDATION_ERROR",
  "message": "Plain language message explaining failure",
  "details": "..."
}
```

---

# Feature Implementation Status

Baseline tracked against [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md).

## Completed

### Input
- [x] Upload CSV (tested via `test_validate_and_save_valid_csv`)
- [x] Upload Excel (.xlsx, multi-sheet aware) (tested via `test_validate_and_save_valid_xlsx`)
- [x] Upload tabular JSON (tested via `test_validate_and_save_valid_json`)
- [x] File size/row limit enforcement with clear error message (tested via `test_rejection_oversized_file`, `test_security_excel_decompression_guard`)

### Data Understanding
- [x] Format & encoding detection (tested via `test_profile_sample_csv`, `test_three_format_profile_parity`)
- [x] Schema/column detection (tested via `test_profile_sample_csv`, `test_profile_sample_xlsx`, `test_profile_sample_json`)
- [x] Type inference (numeric / date / categorical / id / text) (tested via `test_three_format_profile_parity`)
- [x] Data profile: row/column count, null %, duplicate %, unique counts (tested via `test_profile_sample_csv`, parity tests)

---

### Cleaning
- [x] Remove duplicate rows (whole-row or by key column) (`backend/tools/clean.py:drop_duplicates`, wired in `pipeline.py`)
- [x] Handle missing values (mean/median/mode/drop/fill-value) (`backend/tools/clean.py:handle_missing`, wired in `pipeline.py`)
- [x] Fix obvious type mismatches (numbers stored as text) (`backend/tools/clean.py:fix_type_mismatches`, wired in `pipeline.py`)
- [x] Standardize inconsistent date formats (`backend/tools/clean.py:standardize_dates`, wired in `pipeline.py`)

### Transformation
- [x] Rename/reorder columns (`backend/tools/transform.py:rename_columns`, wired in `pipeline.py`)
- [x] Filter rows by condition (`backend/tools/transform.py:filter_rows`, wired in `pipeline.py`)
- [x] Basic derived columns (`backend/tools/transform.py:add_derived_column`, wired in `pipeline.py`)

### Aggregation
- [x] Group by + sum/avg/count/min/max (`backend/tools/aggregate.py:groupby_aggregate`, wired in `pipeline.py`)
- [x] Sort ascending/descending (`backend/tools/aggregate.py:sort_values`, wired in `pipeline.py`)
- [x] Top-N / bottom-N (`backend/tools/aggregate.py:top_n`, wired in `pipeline.py`)

### Visualization
- [x] Bar chart (`backend/tools/chart.py:bar_chart`, wired in `pipeline.py`)
- [x] Line chart (`backend/tools/chart.py:line_chart`, wired in `pipeline.py`)
- [x] Pie chart (`backend/tools/chart.py:pie_chart`, wired in `pipeline.py`)

### Validation
- [x] Row-count sanity check (`validator.py:_check_row_count_nonzero`)
- [x] Row-explosion guard — max 10x expansion (`validator.py:_check_row_count_not_exploded`)
- [x] Post-clean null check — nulls must not increase (`validator.py:_check_post_clean_null_drop`)
- [x] "Requested output exists" check — columns and chart files (`validator.py:_check_requested_output_exists`)
- [x] Bounded auto-retry loop — explicit for-loop (max 2 retries) in `pipeline.py:DataWisePipeline.run()` [FIX F2]

### Output
- [x] Export result dataset (CSV, Excel .xlsx, JSON) (`backend/core/output.py:export_result_file`)
- [x] Download cleaned/processed file with path-traversal guard (`backend/api/routes.py:download_file`)
- [x] Result table preview serialization (NaN→None, ISO dates) (`backend/core/output.py:format_table_preview`)
- [x] Chart file generation and session-safe download serving (`backend/tools/chart.py`, `backend/api/routes.py`)
- [x] Plain-English "what I did" telemetry-grounded summary (`backend/core/output.py:synthesize_plain_english_summary`)
- [x] Sanitized plain-English error messages without raw stack traces (`backend/core/pipeline.py`)

### Trust & Transparency
- [x] Executed plan serialization on `PipelineOutput`
- [x] Per-step telemetry (rows before/after, columns before/after, tool summary, execution time) on `PipelineOutput`

---

## Partially Completed

### Instruction Understanding
- [~] Parse prompt into structured objectives: Deterministic heuristic parser implemented (`backend/core/intent.py`); full dual-provider LLM parser is Phase 4 concern.
- [~] Generate executable plan from objectives: Heuristic planner implemented (`backend/core/planner.py`); full LLM planner is Phase 4 concern.

---

## Completed (Phase 7 — Frontend)

### UI Layer (`frontend/app.py` — Streamlit 1.64.0)
- [x] File upload widget (CSV / XLSX / JSON, 50 MB limit display)
- [x] Natural-language prompt text area with format selector (CSV/Excel/JSON)
- [x] Animated progress bar during pipeline execution with per-stage labels
- [x] **📋 Preview tab** — paginated `st.dataframe` of first 50 rows
- [x] **📈 Charts tab** — inline PNG chart images fetched from session via API
- [x] **🗂 Execution Plan tab** — objectives, step cards with tool name, description, expected output, and telemetry (rows before/after, columns before/after, elapsed ms)
- [x] **✅ Validation tab** — per-check pass/fail with detail text and retry count
- [x] **📥 Downloads tab** — `st.download_button` for CSV, Excel, JSON, and chart PNGs (fetched from backend via `/api/pipeline/download/{session_id}/{filename}`)
- [x] Summary box with plain-English "what I did" narrative
- [x] Status badge (Success / Partial Success / Needs Clarification / Failed)
- [x] Five top-level metric cards (result rows, columns, steps run, checks passed, checks failed)
- [x] Clarification panel — surfaces `NEEDS_CLARIFICATION` prompts cleanly
- [x] Structured error display — error code + plain-English message, no stack traces
- [x] Sidebar with capability list and supported-format pills
- [x] Dark premium theme (Inter font, glassmorphism cards, gradient hero banner, hover micro-animations)

## Completed (Phase 8 — Integration, Security & Hardening)

### Functional Regression
- [x] All 163 tests pass across 16 test files (`pytest --tb=no -q`: `163 passed, 2 warnings in 4.08s`)
- [x] Zero regressions against any Phase 1–7 acceptance criterion

### New E2E Scenarios
- [x] **Transform-only prompt** — plan contains transform step only; no clean step injected (`test_scenario_1_transform_only_no_cleaning`)
- [x] **Chart-only prompt** — chart file produced; preview table returned (`test_scenario_2_chart_only_prompt`)
- [x] **Ambiguous → NEEDS_CLARIFICATION → resubmission → success** (`test_scenario_3_ambiguous_clarification_resubmission`)

### Adversarial Security Tests (REAL probes against running backend)
- [x] Path traversal via crafted upload filename — sanitized to `input.csv` (`test_upload_path_traversal_filename_sanitized`)
- [x] Path traversal in download `session_id` — `HTTP 400` confirmed in server log (`test_download_traversal_tokens_in_session_id_rejected`)
- [x] Path traversal in download `filename` — `HTTP 400` confirmed in server log (`test_download_traversal_tokens_in_filename_rejected`)
- [x] Non-UUID `session_id` on download — `HTTP 400` (`test_download_invalid_uuid_session_id_rejected`)
- [x] Disallowed extension (`.py`) on download — `HTTP 400` (`test_download_disallowed_extension_rejected`)
- [x] Excel decompression bomb (6 M cells) — rejected with "exceeds maximum cell limit" message (`test_excel_decompression_bomb_rejected`)
- [x] Disallowed file extension (`.exe`) on upload — rejected (`test_disallowed_file_extensions_rejected`)
- [x] Oversized file (50 MB+) — rejected (`test_oversized_file_rejected`)
- [x] Prompt injection via adversarial column values — content confined to data layer, never executed (`test_adversarial_content_confined_to_tool_registry`)
- [x] LLM budget hard cap (`MAX_LLM_CALLS_PER_REQUEST = 6`) — `LLMBudgetExceededError` returned cleanly (`test_llm_budget_exhaustion_handled_cleanly`, `test_llm_budget_exhaustion_raises_on_error`)
- [x] Retry loop hard cap (≤ 3 total) with always-failing validate() mock — loop ran exactly 3 times (`test_bounded_retry_loop_hard_ceiling`)
- [x] Session isolation — Session B cannot read Session A's artifacts (`test_concurrent_sessions_isolated`)

### Scale Benchmark
- [x] 500 000-row synthetic CSV processed in **0.82 s** (PRD target: ≤ 60 s)

---

## Not Implemented (Phase 2+ Features)

### Instruction Understanding
- [ ] LLM-backed intent understanding & clarifying questions — full dual-provider LLM integration (Phase 4 scope, heuristic parser currently active)

### Phase 2 Features
- [ ] PDF / DOCX / OCR input formats
- [ ] Correlation analysis, distribution summaries
- [ ] Regression / classification (scikit-learn)
- [ ] Conversational follow-up refinement
- [ ] Auto-generated PDF/DOCX report


---

## Phase 11 — Image Processing Call Chain

1. **Stage 1 (Upload & Session Isolation):** InputManager.validate_and_save() saves raw upload to workspace/sessions/{sid}/input{ext}.
2. **Stage 1.5 (Detection & Registry Routing):** detect_file() sniffs magic bytes (JPEG, PNG, GIF, BMP, WEBP, TIFF) and routes to ImageProcessor via ProcessorRegistry.
3. **Stage 1b (Image Profiling):** ImageProcessor.profile() safely loads metadata (dimensions, mode, EXIF) while enforcing Image.MAX_IMAGE_PIXELS decompression-bomb protection.
4. **Stage 2 & 3 (Intent & Planning):** planner._steps_for_image() maps prompt objectives to image tools (
esize, crop, 
otate, convert_format, compress, extract_metadata, extract_text_ocr).
5. **Stage 4 (Execution):** ImageProcessor.execute() executes operations using Pillow.
6. **Stage 5 (Validation):** ImageProcessor.validate_output() executes operation-specific checks (exact dimension matching, rotation corner-marker tracking, format verification).
7. **Stage 6 (Export):** ImageProcessor.export() saves the final image to disk with format conversion and compression optimization.

---

## Phase 12 — Audio Processing Call Chain (Branch A: Full Manipulation with FFmpeg)

1. **Stage 1 (Upload & Session Isolation):** `InputManager.validate_and_save()` verifies file extension (`.wav`, `.mp3`) against `SUPPORTED_EXTENSIONS` and saves raw upload to `workspace/sessions/{sid}/input{ext}`.
2. **Stage 1.5 (Detection & Registry Routing):** `detect_file()` sniffs magic bytes (`RIFF...WAVE` / `ID3` / frame sync) and routes to `AudioProcessor` via `ProcessorRegistry`.
3. **Stage 1b (Audio Profiling):** `AudioProcessor.profile()` loads duration, sample rate, channels, sample width, and bitrate using `mutagen` and `wave`.
4. **Stage 2 & 3 (Intent & Planning):** `planner._steps_for_audio()` maps prompt objectives to audio tools (`extract_metadata`, `trim`, `convert_format`, `compress`).
5. **Stage 4 (Execution):**
   - Resolves FFmpeg binary via `backend.core.ffmpeg_locator`.
   - For `extract_metadata`: returns structured audio details.
   - For manipulation (`trim`, `convert_format`, `compress`): executes real FFmpeg subprocess, producing processed audio in session workspace.
6. **Stage 5 (Validation):** `AudioProcessor.validate_output()` executes non-vacuous checks: tolerance-bounded duration comparison (`abs(dur - expected) < 0.1s`), format matching, and compression checks.
7. **Stage 6 (Export):** `AudioProcessor.export()` copies processed audio to session result file (`result.wav` / `result.mp3`), preserving format for download.
8. **Frontend Display:** `frontend/app.py` renders metadata chips and interactive `st.audio` playback player for the processed audio file.

---

## Phase 12 — Video Processing Call Chain (Branch A: Full Manipulation with FFmpeg)

1. **Stage 1 (Upload & Session Isolation):** `InputManager.validate_and_save()` verifies file extension (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`) against `SUPPORTED_EXTENSIONS` and saves raw upload to `workspace/sessions/{sid}/input{ext}`.
2. **Stage 1.5 (Detection & Registry Routing):** `detect_file()` sniffs magic bytes (`ftyp`, `ftypqt`, `RIFF...AVI `, or EBML header `\x1a\x45\xdf\xa3`) and routes to `VideoProcessor` via `ProcessorRegistry`.
3. **Stage 1b (Video Profiling):** `VideoProcessor.profile()` probes duration, resolution (width x height), frame rate, video codec, and audio codec using `ffprobe`.
4. **Stage 2 & 3 (Intent & Planning):** `planner._steps_for_video()` maps prompt objectives to video tools (`extract_metadata`, `trim`, `extract_frame`, `resize`, `convert_format`, `compress`, `extract_audio`).
5. **Stage 4 (Execution):**
   - Resolves FFmpeg binary via `backend.core.ffmpeg_locator`.
   - Executes requested tool using FFmpeg (`trim`, `extract_frame`, `resize`, `convert_format`, `compress`, `extract_audio`), outputting processed media to session workspace.
6. **Stage 5 (Validation):** `VideoProcessor.validate_output()` verifies operation results: tolerance-bounded duration checks for trim (`< 0.25s`), dimension matching for resize, Pillow inspection for extracted frames, and format checks.
7. **Stage 6 (Export):** `VideoProcessor.export()` ensures output format defaults to source container format (`result.mp4` / `result.webm` / `result.png`), preserving the file for session download.
8. **Frontend Display:** `frontend/app.py` renders `VIDEO` category badge, stream metrics (resolution, duration), and live `st.video` (or `st.image` for extracted frames) playback widget.

---

## Phase 13 — Archive Processing Call Chain

1. **Stage 1 (Upload & Session Isolation):** `InputManager.validate_and_save()` verifies file extension (`.zip`, `.tar`, `.gz`, `.tgz`) and saves upload to `workspace/sessions/{sid}/input{ext}`.
2. **Stage 1.2 (Archive Security Guard):** `validate_archive_security()` inspects archive headers and central directories *before* extraction:
   - Validates every member against Zip-Slip path traversal attacks (`..`, absolute paths, prefix escapes).
   - Validates declared uncompressed size against the 500 MB limit (Archive Bomb protection).
   - Validates entry count does not exceed 10,000 files.
3. **Stage 1.5 (Detection & Registry Routing):** `detect_file()` sniffs magic bytes (`PK\x03\x04` for ZIP, `ustar` for TAR, `\x1f\x8b` for GZ) and routes to `ArchiveProcessor`.
4. **Stage 1b (Archive Profiling):** `ArchiveProcessor.profile()` inspects members, computes total uncompressed size, counts entries, sniffs member magic bytes, and returns archive schema.
5. **Stage 2 & 3 (Intent & Planning):** `planner._steps_for_archive()` maps objectives to `list_contents` or `extract_and_process`.
6. **Stage 4 (Execution):**
   - Inside a sandboxed `SafeArchiveWorkspace`, extracts validated archive members.
   - For `extract_and_process`: routes each member to its respective domain processor (e.g. tabular, image, doc) according to prompt objectives.
   - Re-packages processed and preserved members into a secure destination archive (`result.zip` / `result.tar` / `result.gz`).
   - Cleans up working extraction directory unconditionally in `finally` block.
7. **Stage 5 (Validation):** `ArchiveProcessor.validate_output()` verifies the output archive exists, is non-empty, and matches original entry count.
8. **Stage 6 (Export):** `ArchiveProcessor.export()` ensures result archive is saved as `result.zip` (or matching format).
9. **Frontend Display:** `frontend/app.py` renders `ARCHIVE` category badge, entry inspection preview table (`Filename`, `Category`, `Action`, `Size`), and single-click archive download.

---

## Phase 13 — Universal Multi-File / Batch Processing Call Chain

1. **Stage 1 (Multi-File Ingestion):** `POST /api/pipeline/run` receives `files: list[UploadFile]`. Files are written into a session-isolated batch directory.
2. **Stage 2 (Magic-Byte Sniffing & Categorization):** Each file is independently sniffed (`detect_file_category`).
3. **Stage 3 (Batch Planning & Execution):**
   - `DataWisePipeline.run_batch()` loops through all files.
   - If the user prompt targets a specific category (e.g. image resize or tabular cleaning), matching files are processed via their domain processor; non-matching files are preserved and marked `excluded`.
   - Results for each file are tracked as `BatchItemResult` (status, details, duration).
4. **Stage 4 (Partial Success Aggregation):** Computes `BatchSummary` (`total_files`, `succeeded_count`, `failed_count`, `excluded_count`). Overall pipeline status is set to `success` or `partial_success`.
5. **Stage 5 (Consolidated Packaging):** Processed files are bundled into a safe, Zip-Slip-protected `result.zip` using `create_safe_archive`.
6. **Frontend Display:** `frontend/app.py` renders batch metric breakdown (e.g. `2/2 Files Processed`), a rich batch results status table, and direct download for the batch ZIP package.

