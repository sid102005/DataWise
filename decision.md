# DataWise — Technical Decision History (decision.md)

This document records all meaningful architectural, engineering, library, model, implementation, and security decisions for **DataWise**.

---

## Decision: 5-Stage Decoupled State Machine Architecture

**Date:** 2026-09-24

**Decision:**
Adopt a hand-rolled, decoupled 5-stage state machine (`Data Understanding` → `Intent Understanding` → `Task Planning` → `Execution` → `Validation` → `Output Generation`) instead of importing heavy agentic frameworks (such as LangChain, LlamaIndex, or AutoGen).

**Context:**
The DataWise PRD and flow specification define a clear linear loop with bounded auto-retry: Understand → Plan → Execute → Validate → Deliver. We must build a system that is transparent, deterministic, testable, and easy to debug without hidden framework abstractions or unexpected prompt chains.

**Reason:**
Frameworks like LangChain introduce significant abstraction overhead, frequent breaking changes, difficult debugging surfaces, and unconstrained execution loops. A dedicated Python state machine with explicit Pydantic models for each stage ensures exact control over the execution flow, state transitions, validation boundaries, and error recovery.

**Alternatives Considered:**
- **LangChain / LangGraph:** High abstraction, heavy dependencies, complex debugging of internal prompt flows.
- **LlamaIndex:** Primarily optimized for RAG/vector retrieval rather than deterministic data manipulation pipelines.
- **Monolithic Script:** Fast to prototype, but fails modularity requirements (violates G5: ability to add formats/operations without rewriting core loop).

**Why This Approach:**
The 5-stage loop maps directly to the functional requirements (FR1–FR7) and enables isolated unit and integration testing of every stage. Antigravity missions can target each stage independently.

**Library / Technology / Model:**
Python 3.14, Pydantic v2, FastAPI.

**Why This Library / Technology / Model:**
Pydantic v2 provides robust runtime validation and JSON schema generation for structured planning outputs. FastAPI provides high-performance asynchronous API endpoints with automatic OpenAPI documentation.

**Impact:**
Shapes the entire backend directory structure (`backend/core/`, `backend/models/`, `backend/api/`).

**Trade-offs / Limitations:**
Requires manual implementation of state transitions, retry loops, and plan revision handlers, rather than relying on pre-built agent graph libraries.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/core/understanding.py`
- `backend/core/intent.py`
- `backend/core/planner.py`
- `backend/core/executor.py`
- `backend/core/validator.py`
- `backend/core/output.py`
- `backend/models/schemas.py`

---

## Decision: Strict Separation of LLM Reasoning and Data Execution

**Date:** 2026-09-24

**Decision:**
Strictly prohibit the LLM from manipulating raw data or computing numeric answers directly. All data ingestion, profiling, cleaning, transformation, aggregation, statistics, and visualizations must be executed exclusively by pure, deterministic Python functions in the tool layer (`backend/tools/`). The LLM is restricted to understanding intent, building structured step lists, explaining actions, and answering clarifying questions.

**Context:**
A critical failure mode of AI data tools is LLM hallucination: generating believable but false numbers or corrupted tables when asked to process tabular data directly in prompt context. Furthermore, sending large datasets into LLM context windows causes excessive latency, huge token costs, and context overflow.

**Reason:**
Deterministic libraries like pandas, numpy, and openpyxl are mathematically sound, fast, and testable. The LLM only needs to receive the metadata profile (schema, column types, null counts, sample head) to formulate a verified plan.

**Alternatives Considered:**
- **In-prompt data transformation:** Passing raw CSV text into the LLM and asking it to output cleaned CSV text. Rejected due to severe hallucination risk, token limits, and performance collapse.
- **Unrestricted dynamic code generation (`eval()` / `exec()`):** Allowing the LLM to write arbitrary Python code executed directly on the host. Rejected for MVP due to security vulnerabilities, potential for infinite loops, and unreliability.

**Why This Approach:**
It guarantees mathematical correctness, provides a 100% audit trail, respects privacy (raw rows don't need to be transmitted to the LLM), and guarantees that every operation can be unit-tested with pytest.

**Library / Technology / Model:**
`pandas`, `numpy`, `openpyxl`, `python-dateutil`.

**Why This Library / Technology / Model:**
Standard industry-grade Python data processing stack with pre-compiled wheels for Python 3.14 on Windows.

**Impact:**
All data transformations run inside `backend/tools/` (`clean.py`, `transform.py`, `aggregate.py`, `chart.py`).

**Trade-offs / Limitations:**
The tool layer must define explicit functions and parameters for all supported operations. Unsupported edge-case operations require extending the tool layer or using constrained sandbox code execution in later phases.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/tools/clean.py`
- `backend/tools/transform.py`
- `backend/tools/aggregate.py`
- `backend/tools/chart.py`
- `backend/core/executor.py`

---

## Decision: Dual-Provider LLM Abstraction (Gemini & Anthropic) with Deterministic Fallback

**Date:** 2026-09-24

**Decision:**
Implement a lightweight LLM adapter interface supporting Google Gemini (default in Antigravity ecosystem) and Anthropic Claude via structured JSON schemas, accompanied by a deterministic rule-based heuristic planner fallback.

**Context:**
The system must parse natural language instructions into structured step lists (`Plan`) adhering to strict Pydantic schemas. Additionally, for automated testing and offline environments without API keys, the core loop must still function deterministically on standard test commands (e.g. "clean data and rank top 10 by revenue").

**Reason:**
Structured output guarantees that the planner generates step names and argument dictionaries that map 1:1 to verified tool functions. The rule-based fallback ensures comprehensive CI/CD testability without incurring API costs or failing when API keys are absent.

**Alternatives Considered:**
- **Single provider hardcoded:** Brittle; locks the system to one vendor.
- **Unstructured text prompts with regex parsing:** Prone to parsing failures and unexpected syntax errors.

**Why This Approach:**
Ensures high availability, developer convenience during local testing, and strict adherence to schemas.

**Library / Technology / Model:**
Google Gemini API / Anthropic Claude API, Pydantic v2.

**Why This Library / Technology / Model:**
Industry standard models with native JSON Schema / Function Calling support.

**Impact:**
Affects `backend/core/intent.py`, `backend/core/planner.py`, and `backend/core/output.py`.

**Trade-offs / Limitations:**
Requires maintaining provider client wrappers and prompt templates for schema compliance.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/core/intent.py`
- `backend/core/planner.py`
- `backend/core/llm_provider.py`

---

## Decision: In-Process Isolated Session Workspace and Local Artifact Storage for MVP

**Date:** 2026-09-24

**Decision:**
Store uploaded files, intermediate step dataframes, and generated artifacts in isolated per-session directories under a dedicated workspace directory (e.g. `workspace/sessions/{session_id}/`), tracked in-memory with session IDs.

**Context:**
MVP requires handling tabular uploads (CSV, Excel, JSON) up to 50MB and producing downloadable cleaned files, charts, and summary reports. Cloud storage (S3/GCS) adds unnecessary infrastructure overhead for local development and initial verification.

**Reason:**
Simple, fast, zero external service dependencies, easily inspectable during development, and trivial to clean up on session expiration.

**Alternatives Considered:**
- **Cloud S3 / GCS Storage:** Over-engineering for Phase 1 MVP.
- **Pure in-memory storage:** Inconvenient for file downloads, inspection, and large files.

**Why This Approach:**
Maintains session isolation, guarantees security boundary per session, and enables instant download of outputs.

**Library / Technology / Model:**
Python standard library `pathlib`, `tempfile`, `uuid`.

**Why This Library / Technology / Model:**
Zero third-party dependencies, cross-platform compatibility (Windows/Linux/macOS).

**Impact:**
Affects `backend/api/` and `backend/core/input_manager.py`.

**Trade-offs / Limitations:**
Not horizontally scalable across multiple server nodes without a shared filesystem or object store (planned for Phase 2/3).

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/core/input_manager.py`
- `backend/api/routes.py`

---

## Decision: Metadata-Only DataProfile for LLM Privacy and Context Isolation

**Date:** 2026-09-25

**Decision:**
The `DataProfile` object generated by Stage 1 and transmitted to the LLM in Stage 2/3 (Phase 4+) shall contain **strictly metadata only** (column names, inferred semantic types, null percentages, duplicate percentages, row counts, and structural quality flags). Under default operation, **no raw cell values, sample row heads, or record contents** shall be sent to external LLM APIs.

**Context:**
The previous entry "Strict Separation of LLM Reasoning and Data Execution" noted that raw rows "don't need to be transmitted to the LLM", but concurrently mentioned that a "sample head" could be provided. This represented a conceptual ambiguity regarding data confidentiality and token footprint.

**Reason:**
Sending actual cell values creates potential privacy/compliance hazards (accidental transmission of PII, sensitive business metrics, or confidential transactions) and inflates token usage. Planning requires understanding schema types and data quality anomalies, not reading raw records. For example, knowing that column `Age` has 12% nulls and inferred type `numeric` is sufficient for the planner to generate `handle_missing(column="Age", strategy="median")` without ever seeing any person's age.

**Alternatives Considered:**
- **Transmit Top 5 Sample Rows:** Common in generic LLM data agents, but exposes private user records to third-party model providers and risks prompt injection from adversarial cell content.
- **Allow User Opt-In for Sample Data:** Defer to Phase 3/Enterprise scope if categorical value disambiguation genuinely requires it.

**Why This Approach:**
Upholds zero-PII exposure by default, minimizes token consumption, protects against malicious prompt injection inside tabular data, and aligns directly with PRD §8 (Security/Privacy non-functional requirements).

**Library / Technology / Model:**
Pydantic v2 (`DataProfile`, `ColumnInfo` in `backend/models/schemas.py`).

**Why This Library / Technology / Model:**
Strict schema enforcement with `extra="forbid"` guarantees that raw rows cannot inadvertently slip into profile payloads.

**Impact:**
Clarifies Stage 1 profiling (`backend/core/understanding.py`) and prompt construction in Stage 2/3 (`backend/core/intent.py`, `backend/core/planner.py`).

**Trade-offs / Limitations:**
The LLM cannot inspect specific categorical strings unless explicitly summarized in metadata (e.g. distinct category lists for low-cardinality columns).

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/models/schemas.py`
- `backend/core/understanding.py`

---

## Decision: Single-Worker Uvicorn Deployment Constraint for In-Process Session State

**Date:** 2026-09-25

**Decision:**
Constrain the FastAPI backend deployment explicitly to a **single worker process** (`workers=1`). Running with `--workers > 1` is strictly unsupported for the MVP architecture.

**Context:**
The MVP architecture uses an in-process session manager and local filesystem session isolation (`workspace/sessions/{session_id}/`). If Uvicorn or Gunicorn spawns multiple OS worker processes, in-memory state (session metadata, plan revisions, intermediate state machine progress) is partitioned across independent Python processes without inter-process synchronization.

**Reason:**
Subsequent HTTP requests for the same session (such as polling status, downloading results, or answering clarification questions) routed to a different worker process would fail with `SESSION_NOT_FOUND` or produce corrupt state transitions.

**Alternatives Considered:**
- **External Redis / Memcached State Store:** Adds infrastructure complexity, operational overhead, and external dependency requirements before Phase 1 is even proven.
- **File-Locked Session Database (SQLite):** Adds locking overhead and concurrency management not needed for single-user MVP validation.

**Why This Approach:**
Maintains zero external service dependencies while providing 100% deterministic session isolation.

**Library / Technology / Model:**
Uvicorn / FastAPI.

**Why This Library / Technology / Model:**
Native async event loop easily handles concurrent I/O within a single worker process without multi-process hazards.

**Impact:**
Documented in `backend/main.py` entry point configuration and startup assertions.

**Trade-offs / Limitations:**
Cannot utilize multi-core parallelism for CPU-bound data operations in MVP; scaling requires horizontal migration to Redis/Postgres in Phase 3.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/main.py`
- `backend/config.py`

---

## Decision: Canonical Test Fixture Design and Ground Truth Specification

**Date:** 2026-09-25

**Decision:**
Establish a single immutable set of canonical test fixtures (`sample.csv`, `sample.xlsx`, `sample.json`, `expected_sample_profile.json`, `malformed.csv`, `oversized_placeholder.txt`, `path_traversal_attempt.csv`) in `tests/fixtures/`. For the primary dataset (50 rows, 6 columns), all properties (4 exact duplicate rows, 6 missing Age rows, mixed Date formats, unambiguous top-10 Purchases, and 4 distinct regions) are mathematically fixed and audited by hand.

**Context:**
Testing multi-stage data pipelines across multiple implementation phases requires reliable ground truth. If test fixtures are small, ambiguous, or generated ad-hoc by each phase, subtle bugs (such as ranking ties, order-dependent deduplication, or inconsistent format parsing) produce flaky or misleading tests.

**Reason:**
50 rows provides sufficient depth for top-N ranking (top 10 vs remaining 40) and realistic null/duplicate proportions. Placing duplicate rows strictly outside the top-10 purchase tiers and keeping them free of missing values guarantees that:
1. Top-10 queries yield identical, deterministic results regardless of whether deduplication occurs before or after ranking.
2. Deduplication reduces row count from 50 to 46 without altering the count of null values in `Age` (which remains 6).
3. The mixed date formats (33 ISO `YYYY-MM-DD` and 17 `DD/MM/YYYY`) provide a reliable test bed for format inference and clarification prompts.

**Alternatives Considered:**
- **Randomly Generated Synthetics:** Non-deterministic; impossible to maintain hardcoded assertions in test suites.
- **Small 10-Row Fixture:** Inadequate to test Top-10 truncation or realistic duplicate/null interactions.

**Why This Approach:**
Provides an immutable benchmark against which all pipeline stages (Stage 1 profiling, Stage 4 tool execution, Stage 5 validation) can be verified with exact numerical assertions.

**Library / Technology / Model:**
`pandas`, `openpyxl`, JSON.

**Why This Library / Technology / Model:**
Covers the three primary supported tabular formats in Phase 1 MVP.

**Impact:**
All test suites across all project phases (`backend/tests/`) rely exclusively on these fixtures.

**Trade-offs / Limitations:**
Static dataset cannot test arbitrary schema variations; edge cases must be supplemented with targeted synthetic unit tests where appropriate.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `tests/fixtures/sample.csv`
- `tests/fixtures/sample.xlsx`
- `tests/fixtures/sample.json`
- `tests/fixtures/expected_sample_profile.json`
- `tests/fixtures/README.md`
- `tests/fixtures/malformed.csv`
- `tests/fixtures/oversized_placeholder.txt`
- `tests/fixtures/path_traversal_attempt.csv`

---

## Decision: Fixed Internal Filename Storage Strategy to Prevent Path Traversal (FIX F3)

**Date:** 2026-09-25

**Decision:**
Store all uploaded datasets strictly under fixed, deterministic internal filenames derived solely from the session identifier and the validated file extension (`workspace/sessions/{session_id}/input{ext}`, e.g., `input.csv`, `input.xlsx`, or `input.json`). The original user-provided filename is recorded exclusively as display metadata in `metadata.json` and must never be concatenated, joined, or utilized in filesystem path construction.

**Context:**
Allowing user-supplied filenames in filesystem operations introduces Critical Path Traversal vulnerabilities (e.g. `../../../evil.csv`). If un-sanitized, attackers can overwrite system binaries, access unauthorized files, or escape container boundaries.

**Reason:**
Eliminates an entire class of file-system path traversal vulnerabilities by design. Rather than relying on fragile regex or sanitization heuristics (e.g. stripping `../` which can be bypassed via nested or encoded characters), the application guarantees that internal paths are 100% synthetic and isolated within `workspace/sessions/{session_id}/`.

**Alternatives Considered:**
- **Regex Filename Sanitization (`re.sub`):** Fragile; can fail with alternate encodings, null bytes, or OS-specific filename edge cases.
- **`werkzeug.utils.secure_filename`:** Better, but still allows attacker-influenced names and potential collisions within a session.

**Why This Approach:**
Absolute security guarantee: the internal path never incorporates user input. Verified by real assertion in `backend/tests/test_input_manager.py::test_security_path_traversal_prevention`.

**Library / Technology / Model:**
Python standard library `pathlib.Path`, `uuid`.

**Why This Library / Technology / Model:**
Zero third-party dependencies with cross-platform filesystem guarantees.

**Impact:**
Implemented in `backend/core/input_manager.py` (`InputManager.validate_and_save`).

**Trade-offs / Limitations:**
The user's original filename is preserved only in metadata and must be mapped back when generating downloadable outputs.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/core/input_manager.py`
- `backend/tests/test_input_manager.py`

---

## Decision: Pre-Load Decompressed Cell-Count Threshold for Excel Files (FIX F4)

**Date:** 2026-09-25

**Decision:**
Enforce a pre-load decompressed cell-count ceiling of **5,000,000 cells** across all worksheets in uploaded Excel (`.xlsx`) files before loading them into memory with pandas. Inspection must occur using `openpyxl` in `read_only=True` mode immediately after upload validation.

**Context:**
Excel `.xlsx` files are zip archives containing compressed XML worksheets. A malicious file ("decompression bomb") can have a tiny compressed on-disk footprint (e.g., 200KB) but expand to billions of rows and columns when decompressed into memory, crashing the Python process via Out-Of-Memory (OOM) or causing Denial of Service (DoS).

**Reason:**
A standard file-size check (50MB) does not protect against zip-bomb expansion. By using `openpyxl.load_workbook(read_only=True)`, the workbook's XML dimension headers can be inspected in constant time with negligible memory footprint. Calculating `total_cells = sum(sheet.max_row * sheet.max_column)` allows the system to identify and reject catastrophic files before pandas attempts to allocate DataFrame memory buffers.

**Alternatives Considered:**
- **OS-Level Memory Limits (`resource.setrlimit`):** Platform-specific (Linux only), unavailable on Windows host.
- **Process Spawning with Memory Watchdogs:** Substantial engineering complexity for Phase 1/MVP.

**Why This Approach:**
Lightweight, cross-platform, deterministic, and catches decompression bombs before any significant memory is allocated.

**Library / Technology / Model:**
`openpyxl` (`load_workbook(read_only=True)`).

**Why This Library / Technology / Model:**
Already a core dependency for Excel support; streaming read-only mode avoids memory inflation.

**Impact:**
Implemented in `backend/core/input_manager.py` (`InputManager.validate_and_save`).

**Trade-offs / Limitations:**
Workbooks with sparse or incorrectly tagged dimension headers might report estimated cells higher than actual populated cells; however, 5,000,000 cells exceeds reasonable single-sheet MVP datasets by a wide margin (e.g. 50,000 rows × 100 columns).

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/core/input_manager.py`
- `backend/tests/test_input_manager.py`

---

## Decision: Strict Pre-Execution Column Validation for Tool Functions (FIX F5)

**Date:** 2026-09-25

**Decision:**
Every function in the tool layer (`backend/tools/clean.py`, `backend/tools/transform.py`, `backend/tools/aggregate.py`, `backend/tools/chart.py`) that accepts a column name or list of columns must validate that every referenced column exists in `df.columns` before executing, raising a typed `ToolInputError` if validation fails.

**Context:**
Allowing arbitrary or unvalidated column parameters into pandas operations leads to raw unhandled `KeyError` exceptions, confusing internal stack traces, or silent no-ops. Furthermore, malicious strings (such as `"__proto__"`, SQL-injection style strings, or unexpected symbols) could cause unpredictable behavior if passed down into underlying libraries or formatting templates.

**Reason:**
A clean `ToolInputError` with an explicit message listing available columns provides immediate, actionable feedback to the planning and validation layers. When the Executor dispatches a step, any column mismatch is caught immediately and deterministically before any DataFrame mutation occurs.

**Alternatives Considered:**
- **Relying on Native pandas `KeyError`:** Produces generic, uninformative errors that are difficult for the validation and planner revision loop to diagnose.
- **Silent No-Op or Dropping Missing Columns:** Unacceptable; masks user errors and can corrupt downstream aggregations.

**Why This Approach:**
Provides fail-fast security and deterministic error boundaries. Verified across all tool functions in `backend/tests/test_tools_*.py`.

**Library / Technology / Model:**
Python standard exception hierarchy (`ToolInputError` subclassing `DataWiseError`).

**Why This Library / Technology / Model:**
Seamless integration with FastAPI exception handlers and pipeline error reporting.

**Impact:**
All tool layer functions enforce this check as their first statement.

**Trade-offs / Limitations:**
Adds a small O(k) set lookup per function call, which has negligible overhead compared to DataFrame operations.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/tools/clean.py`
- `backend/tools/transform.py`
- `backend/tools/aggregate.py`
- `backend/tools/chart.py`
- `backend/core/exceptions.py`

---

## Decision: Matplotlib Agg Headless Backend for Deterministic Server-Side Visualization

**Date:** 2026-09-25

**Decision:**
Adopt `matplotlib` configured with the headless `'Agg'` backend (`matplotlib.use("Agg")`) for Phase 1 MVP static chart generation (bar, line, pie), rendering charts to disk as PNG image artifacts. Interactive Plotly charts are deferred to Phase 2/3.

**Context:**
The application must generate downloadable and displayable visual artifacts for bar, line, and pie charts without requiring a desktop display server or GUI event loop (X11 / Wayland / Windows desktop window).

**Reason:**
Matplotlib's `'Agg'` raster backend is headless, rock-solid, thread-safe for file exports, and produces standard PNG image files that can be rendered in any web browser or UI preview component. It requires minimal dependencies and eliminates GUI window-binding errors on server hosts.

**Alternatives Considered:**
- **Plotly (HTML/JSON):** Great for client-side interactivity, but requires bundling JavaScript runtimes or webview renderers. Deferred to future UI polish phases.
- **Seaborn:** Adds an extra dependency layer on top of matplotlib without substantial benefits for MVP basic chart types.

**Why This Approach:**
Boring, reliable, headless, and exports directly to the workspace session directory as standalone image files.

**Library / Technology / Model:**
`matplotlib` (`3.11.2`).

**Why This Library / Technology / Model:**
Industry standard for static Python plotting with pre-compiled wheels for Python 3.14.

**Impact:**
Implemented in `backend/tools/chart.py`.

**Trade-offs / Limitations:**
Generated PNG files are non-interactive; hover tooltips and dynamic zooming are not available in MVP.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/tools/chart.py`
- `backend/tests/test_tools_chart.py`

---

## Decision: Default Missing-Value Imputation Strategy: Median for Numeric, Mode for Categorical

**Date:** 2026-09-25

**Decision:**
When missing value handling is requested without an explicit strategy or when using the default strategy in `handle_missing()`, apply **median** imputation for numeric columns (to maintain robustness against outliers) and automatically fall back to **mode** (most frequent value) for categorical or text columns.

**Context:**
Computing the arithmetic mean on skewed data or integer counts can introduce distorted fractions or extreme sensitivity to outliers. Furthermore, calling numeric aggregation (like mean or median) on text/categorical data crashes with type errors.

**Reason:**
The median is robust against extreme values and preserves the central tendency of numeric distributions. For categorical fields, mode imputation is the only statistically meaningful single-value imputation strategy without training predictive ML models.

**Alternatives Considered:**
- **Mean Default:** Susceptible to outlier distortion (e.g. one massive transaction skews average customer age).
- **Constant Zero/Blank Default:** Distorts distributions and introduces misleading zero spikes.

**Why This Approach:**
Provides sensible, statistically sound defaults without requiring user intervention for routine data prep.

**Library / Technology / Model:**
`pandas`, `numpy`.

**Why This Library / Technology / Model:**
Built-in vectorized methods `Series.median()` and `Series.mode()`.

**Impact:**
Implemented in `backend/tools/clean.py` (`handle_missing`).

**Trade-offs / Limitations:**
Mode imputation on high-cardinality categorical columns with uniform distributions can be arbitrary; complex imputation is left for Phase 2 ML expansions.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md)

**Related Code Files:**
- `backend/tools/clean.py`
- `backend/tests/test_tools_clean.py`


---

## Decision: Stateless Executor and Validator with Allow-Listed Tool Registry (FIX F2)

**Date:** 2026-09-25

**Decision:**
`backend/core/executor.py` and `backend/core/validator.py` are implemented as completely stateless, orchestration-free modules. `execute_plan()` iterates Plan steps exactly once and returns results; `validate()` inspects inputs and returns a `ValidationResult`. Neither module calls the planner, initiates retries, or contains any loop logic beyond iterating the plan steps list. The bounded retry loop (max 2 attempts) is deferred entirely to Phase 6's `pipeline.py`.

The executor dispatches tool calls exclusively through an explicit allow-list registry (`_TOOL_REGISTRY`) mapping `tool_name → callable`. Any `tool_name` not present in the registry raises an `ExecutorError` immediately. Arbitrary function lookup by string (e.g., `getattr`, `globals()`) is intentionally forbidden.

**Context:**
A previous (v1) plan placed the retry loop inside `validator.py`, creating circular coupling (validator → planner → executor). This also split retry-loop ownership across two modules, making the system hard to test and reason about.

**Reason:**
Stateless single-responsibility functions are independently unit-testable with pytest without mocking any other system component. The allow-list registry is a defense-in-depth mechanism: a compromised planner cannot inject calls to arbitrary Python functions by crafting a malicious tool_name string.

**Alternatives Considered:**
- **Dynamic function lookup via `globals()` or `importlib`:** Rejected — allows plan-injection attacks and makes the tool surface unbounded.
- **Retry loop inside `validator.py`:** Rejected — circular dependency, mixed responsibilities, untestable in isolation.

**Why This Approach:**
Guarantees clean separation of concerns: executor dispatches, validator checks, pipeline orchestrates. Each can be tested with a single function call and no mocking.

**Library / Technology / Model:**
Python standard library. `time.monotonic()` for per-step wall-clock telemetry.

**Impact:**
- `backend/core/executor.py`: `execute_plan()`, `list_registered_tools()`, `ExecutorError`.
- `backend/core/validator.py`: `validate()` with 4 named checks.
- `backend/models/schemas.py`: `Step.parameters` extended to `dict[str, str | int | float | bool | list[str] | dict | None]` to support nested structures (`expression_spec`, `mapping`).

**Trade-offs / Limitations:**
The retry loop must be implemented entirely in `pipeline.py` (Phase 6). The allow-list registry requires a deliberate code edit to register new tools — this is a feature, not a bug, but does add a small maintenance step when expanding the tool layer.

**Related Reference Documents:**
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md) (Stage 4, Stage 5)
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md) (§7 FR4, FR5)

**Related Code Files:**
- `backend/core/executor.py`
- `backend/core/validator.py`
- `backend/models/schemas.py`
- `backend/tests/test_executor.py`
- `backend/tests/test_validator.py`

---

## Decision: Pipeline Orchestration with Bounded Retry Loop, LLM-Call Budget, and Path-Safe File Serving (Closes FIX F2, FIX F9, and FIX F3)

**Date:** 2026-09-25

**Decision:**
Stage 1 through Stage 6 are orchestrated strictly within `backend/core/pipeline.py:DataWisePipeline`.
1. **Bounded Retry Loop [CLOSES FIX F2]:** `DataWisePipeline` owns the only retry loop in the entire system. It is implemented as an explicit, bounded `for attempt in range(MAX_RETRIES + 1)` loop with `MAX_RETRIES = 2`. The loop is hard-capped at 3 total attempts (1 initial attempt + 2 retries), regardless of planner return or forced validation failures. Recursive retries are explicitly forbidden to prevent unbounded stack growth and hard-to-trace state divergence. Neither `executor.py`, `validator.py`, nor `planner.py` contain any retry orchestration.
2. **LLM Budget Enforcement [CLOSES FIX F9]:** `DataWisePipeline` enforces a strict per-request LLM call limit (`MAX_LLM_CALLS_PER_REQUEST = 6`). A single `LLMCallCounter` is created per pipeline run and passed across `intent.parse_intent()`, `planner.build_plan()`, and `planner.revise_plan()`. If the budget is exhausted, `LLMBudgetExceededError` is raised and caught, terminating execution gracefully with a clear plain-English explanation rather than silently running up API costs or looping indefinitely.
3. **Path-Safe File Serving [CLOSES FIX F3 END-TO-END]:** File downloads (`GET /api/pipeline/download/{session_id}/{filename}` and alias `/api/download/{session_id}/{filename}`) strictly validate against path traversal BEFORE any filesystem access. Rejects `..`, `/`, and `\\` tokens in parameters immediately with HTTP 400. Strictly validates `session_id` as a UUID4, restricts filename extensions to an allow-list (`result.(csv|xlsx|json)` or chart images `*.png`), and asserts path containment via `file_path.resolve().is_relative_to(session_dir.resolve())` and `is_relative_to(SESSIONS_DIR.resolve())`.
4. **Clarification Short-Circuit:** If `planner.check_ambiguity_and_clarification()` detects ambiguous intent (e.g., underspecified filters or calculations), the pipeline short-circuits immediately before execution, returning HTTP 200 with status `NEEDS_CLARIFICATION`, row count untouched, and a targeted clarifying question.
5. **Error Sanitization Contract:** All exceptions across all pipeline stages are intercepted and mapped to structured, plain-English messages on `PipelineOutput` or `ErrorResponse` (with corresponding HTTP 4xx/5xx status codes). Raw stack traces and internal file paths are logged server-side but never exposed to users.
6. **Deterministic Heuristic Fallback:** Intent understanding and task planning default to rule-based heuristic engines when an LLM client is absent, ensuring 100% offline testability and reliable CI operation while preserving the identical schema contracts for LLM-backed execution in Phase 4.

**Context:**
Previous v1 planning lacked a single source of truth for execution retries and LLM budgeting, creating risks of infinite loops, circular dependencies, budget overruns, and path-traversal vulnerabilities in file downloads.

**Reason:**
Centralizing pipeline flow in a single orchestrator gives full visibility, enforces hard limits, and isolates core business logic into stateless, testable components.

**Alternatives Considered:**
- **Recursive retries in `validator.py` or `planner.py`:** Rejected (circular dependency and unbounded call stacks).
- **Ad-hoc file path concatenation in download endpoint:** Rejected (vulnerable to directory traversal attacks).
- **Direct stack trace returns on pipeline errors:** Rejected (leaks server internals and degrades user trust).

**Why This Approach:**
Provides rock-solid reliability, predictable execution cost, comprehensive security against traversal attacks, and clear plain-English user communications.

**Library / Technology / Model:**
FastAPI, Starlette `FileResponse`, Pydantic V2, Python `pathlib`, `uuid`.

**Impact:**
- `backend/core/pipeline.py`: Orchestrator with explicit bounded retry loop and LLM budget counter.
- `backend/core/output.py`: Result exporter, preview generator, and plain-English summary synthesizer.
- `backend/core/intent.py` & `backend/core/planner.py`: Deterministic fallback planners with clarification check and budget tracking.
- `backend/api/routes.py`: REST endpoints with security validation and path-safe file serving.
- `backend/main.py`: Registers API routes onto FastAPI app.
- `backend/tests/test_output.py`: Output generation unit tests.
- `backend/tests/test_pipeline.py`: Hard retry cap, LLM budget forced excess, and clarification short-circuit tests.
- `backend/tests/test_api_integration.py`: TestClient API integration, path traversal rejection, and error mapping tests.

**Trade-offs / Limitations:**
The heuristic planner uses keyword and metadata matching; complex, multi-layered natural language queries without standard keywords require the LLM-backed path built in Phase 4.

**Related Reference Documents:**
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md) (All Stages)
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md) (§7 FR6, FR7, §8 Reliability/Cost-control)
- [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md) ("Output", "Trust and Transparency")
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `backend/core/pipeline.py`
- `backend/core/output.py`
- `backend/core/intent.py`
- `backend/core/planner.py`
- `backend/api/routes.py`
- `backend/main.py`
- `backend/tests/test_output.py`
- `backend/tests/test_pipeline.py`
- `backend/tests/test_api_integration.py`

---

## Decision: Streamlit Frontend Architecture with Direct API Integration, Session Isolation, and Strict Error Redaction

**Date:** 2026-09-25

**Decision:**
Implement the user-facing interface in `frontend/app.py` using Streamlit (version 1.64.0+), communicating with the backend exclusively over HTTP REST endpoints (`POST /api/pipeline/run`, `GET /api/pipeline/download/{session_id}/{filename}`) via `frontend/client.py`. 

**Strict Error-Redaction & UX Contract:**
The UI enforces strict client-side and transport-level error sanitization via `frontend/helpers.py`:
1. **Omit Internal Details:** The `details` field returned by backend errors (which could contain raw pandas tokenizer messages, OS exceptions, or file coordinates) is completely omitted and never surfaced verbatim to the end user.
2. **Path & Traceback Redaction:** The user-facing `message` field is scrubbed against regex patterns for Windows (`C:\...`) and Unix (`/...`) file paths and multiline tracebacks (`redact_sensitive_paths`), replacing them with safe placeholder tokens (e.g. `[internal path]`).
3. **Structured Badges:** Only standardized `error_code` (e.g., `FILE_VALIDATION_ERROR`, `CONNECTION_ERROR`, `VALIDATION_ERROR`) and human-readable, plain-language text are rendered. Raw JSON payloads and uncaught Python tracebacks are strictly prevented from reaching the UI.
4. **Backend-Down Graceful Handling:** If the backend is unreachable or times out, the client intercepts `requests.exceptions.ConnectionError` and `Timeout`, presenting a clear instructional message rather than a raw Python crash or stack trace.

**Context:**
Per `techstack.md`, Streamlit is the recommended UI for rapid MVP iteration and high-density tabular/chart display. The frontend must fulfill all Phase 1 MVP user interaction requirements: file uploads, free-text prompt input, export format selection, execution telemetry visualization, inline chart rendering, and artifact downloads while ensuring zero internal server details or security-sensitive paths leak to users.

**Reason:**
1. **Decoupled Architecture:** Running Streamlit and FastAPI as separate processes preserves the client-server boundary, enabling future deployment of the frontend (e.g., Streamlit Community Cloud) independently from the backend service.
2. **Complete Transparency:** Exposing execution steps, rows before/after, columns before/after, and check results directly fulfills PRD §7 (FR6/FR7) trust and transparency requirements.
3. **Defense-in-Depth Sanitization:** Even if a backend error message inadvertently includes a local path, the frontend redaction layer guarantees user confidentiality and clean UX.

**Alternatives Considered:**
- **React / Next.js SPA:** Provides greater layout flexibility, but adds substantial build tooling, Node.js dependencies, and development overhead for a data-centric Phase 1 MVP.
- **FastAPI Jinja2 Server-Rendered Templates:** Lower interactivity for streaming status updates, table pagination, and dynamic chart loading without writing extensive vanilla JavaScript.

**Why This Approach:**
Streamlit provides native high-performance components (`st.dataframe`, `st.download_button`, `st.tabs`, `st.metric`) with minimal boilerplate while allowing complete CSS styling customization to deliver a modern, premium dark aesthetic.

**Library / Technology / Model:**
`streamlit` 1.64.0, `requests`, Google Fonts (Inter).

**Impact:**
- `frontend/app.py`: Standalone UI client.
- `frontend/client.py`: Decoupled HTTP API communication.
- `frontend/helpers.py`: Response parsing, path scrubbing, and clarification extractors.
- `frontend/README.md`: Frontend operational guide and configuration.
- `requirements.txt`: Streamlit and transitive dependencies pinned.
- `execution.md`: Documented startup commands, entry points, and completed UI features.

**Trade-offs / Limitations:**
Streamlit executes top-to-bottom on every user interaction (state reruns). To ensure stability, session states (`st.session_state`) are used for storing execution results across re-renders and download clicks.

**Related Reference Documents:**
- [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md) (§6, §7 FR6, FR7)
- [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md)
- [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md) ("UI Layer", "Output", "Trust and Transparency")
- [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md)

**Related Code Files:**
- `frontend/app.py`
- `frontend/client.py`
- `frontend/helpers.py`
- `frontend/README.md`
- `backend/tests/test_frontend_helpers.py`
- `backend/api/routes.py`
- `backend/main.py`
- `execution.md`



---

## Decision: Emergency Fix — Structured Column-Operation NLU (Root Cause H1+H2+H3)

**Date:** 2026-09-26

**Decision:**
Replace keyword-only intent classification with a structured column-operation extraction
layer that fires BEFORE the general keyword map. Add `drop_column` and `add_column` to
`transform.py` and the executor registry. Rewrite `validator.py` to run operation-specific
assertions per step.

**Context:**
Confirmed reproducible bug: user instructs "remove the column of the Phone", UI reports
Success (2 steps run, 4 checks passed) but Phone column remains in output.

**Root Cause:**
- H1 CONFIRMED: `drop_column` not implemented in `transform.py` or registered in executor.
- H2 CONFIRMED: `intent.py` had no patterns for column-drop — prompt classified as CLEAN.
- H3 CONFIRMED: `validator.py` generic-only checks pass even when no transformation ran.

**Fix Summary:**
1. Added `drop_column(df, column)` and `add_column(df, column, default_value)` to `transform.py`.
2. Registered both in `executor.py` `_TOOL_REGISTRY`.
3. Added structured NLU layer to `intent.py` — 4 compiled regex drop patterns, 4 add patterns,
   1 rename pattern, `_ROW_OP_NOUNS` guard to prevent "remove duplicate rows" from matching as
   a column drop. Deduplication prevents multiple patterns matching the same column.
4. Updated `planner.py` `_steps_for_transform()` to parse structured mini-format descriptions
   (`drop_column: X`, `add_column: X`, `rename_column: X to Y`).
5. Rewrote `validator.py` with per-tool operation-specific assertions:
   drop_column (column absent), add_column (column present), rename_columns (old absent + new
   present), filter_rows (all rows satisfy condition), sort_values (monotonic check),
   drop_duplicates (0 duplicates remain), handle_missing (null count), fix_type_mismatches (dtype).

**Invariant Established:**
"A status message is not evidence. The data is the evidence."
Validation MUST assert WHAT CHANGED, not just THAT SOMETHING RAN.

**Regression Suite:**
53 new tests in `backend/tests/test_regression_emergency_fix.py` assert against
reopened exported files. 216/216 tests pass.

**Files Changed:**
- `backend/tools/transform.py`
- `backend/core/executor.py`
- `backend/core/intent.py`
- `backend/core/planner.py`
- `backend/core/validator.py`
- `backend/tests/test_regression_emergency_fix.py` (new)
- `backend/tests/test_executor.py` (updated expected tool set)
- `backend/tests/test_validator.py` (updated for operation-specific checks)
- `test_data/` (6 new fixtures)
- `scripts/generate_test_data.py` (new)


---

## Decision: Phase 9 — Universal Format Scope Expansion & Processor Interface

**Date:** 2026-09-26

**Decision:**
Supersede PRD.md's v1 scope limits (tabular only, 50MB, 500k rows). Implement a FileDetectionLayer that uses magic-byte sniffing (overriding file extensions on mismatch), a ProcessorRegistry, and an abstract FileProcessor interface. Refactor the entire existing 5-stage DataWise tabular pipeline to be the first TabularProcessor conforming to this interface.

**Context:**
The agent must transition from tabular-only to universal document/image/video/audio support. The existing monolithic pipeline.py handled too many concerns.

**Why This Approach:**
- Leaves the proven execution/validation code untouched (thin wrapper).
- Guarantees standard capability contracts via the abstract base class.
- Makes pipeline.py oblivious to data types; it just orchestrates the registered processor.
- Detection mismatch heuristic (magic bytes vs extension) prevents runtime crashes on badly-named files.


---

## Decision: Phase 11 — Image Processing Architecture & Scope Boundaries

**Date:** 2026-09-26

**Decision:**
Implement ImageProcessor conforming to the FileProcessor interface, supporting JPEG, PNG, GIF, BMP, WEBP, and TIFF. Restrict initial image capabilities strictly to structural, pixel-verifiable operations (resize, crop, rotate, format conversion, compression, metadata extraction, OCR gating).

**Dependency Choice (Pillow-Only):**
Pillow 12.3.0 is completely sufficient for all required structural operations. OpenCV was evaluated and rejected: adding OpenCV would introduce heavy C++ binary dependencies and bloated install sizes without any functional benefit for standard 2D manipulation.

**Security Guard (Decompression Bomb Protection):**
Pillow's Image.MAX_IMAGE_PIXELS is explicitly preserved and NEVER disabled (MAX_IMAGE_PIXELS = None is strictly prohibited). Images exceeding this limit are caught and raised as structured FileValidationError to prevent memory exhaustion DOS attacks.

**Deliberate Scope Boundaries (Deferred Vision Capabilities):**
- Vision LLM features (image description, classification) are out of scope: they require external multimodal API keys and cannot be deterministically verified against ground-truth dimensions.
- Background removal is out of scope (requires specialized segmentation networks).
- Batch processing is deferred to Phase 13 (alongside archive processing).


---

---

## Decision: Dynamic Capability-Driven Frontend Architecture

**Date:** 2026-09-27

**Decision:**
Eliminate hardcoded accepted-format lists in the Streamlit frontend (rontend/app.py). Derive the accepted upload formats (	ype=[...] on st.file_uploader), sidebar category badges, and result rendering branches dynamically from a new backend endpoint GET /api/capabilities, backed directly by capabilities.json and ProcessorRegistry. Provide an explicit, safe fallback (['csv', 'xlsx', 'json']) with a prominent visual warning when the backend is offline.

**Context:**
The frontend built in Phase 7 hardcoded 	ype=['csv', 'xlsx', 'json'] in st.file_uploader. When Phase 10 (Document Processor: PDF, DOCX, TXT, MD) and Phase 11 (Image Processor: JPG, PNG, GIF, BMP, WEBP, TIFF) were implemented in the backend, the frontend was never updated. This caused an integration gap where real, verified backend processors could not be reached through the UI because the browser file picker rejected non-tabular files.

**Reason:**
Hardcoded client-side format lists inevitably drift out of sync whenever backend processors are added, updated, or temporarily disabled. By exposing GET /api/capabilities reflecting the single source of truth (capabilities.json + ProcessorRegistry), future format additions (Phase 12 Audio, Phase 13 Video/Archive/Presentation) automatically propagate to the UI without requiring frontend code edits.

**Result Rendering Generalization:**
- **Tabular:** Renders preview st.dataframe with row/column metrics and chart tab.
- **Document:** Renders extracted text in st.text_area with live word and character counters.
- **Image:** Renders inline processed image via st.image with extracted dimension (W × H), format, and mode metadata, verified against the downloaded artifact.
- **Defensive Null-Safety:** Never assumes tabular fields (preview_columns, preview_rows, 	otal_rows) exist on non-tabular payloads.

**Testing Strategy:**
Enforced via ackend/tests/test_frontend_smoke.py using official streamlit.testing.v1.AppTest driving real in-process execution across tabular, document, image, and offline fallback scenarios. 7/7 tests pass.

**Related Code Files:**
- ackend/api/routes.py (GET /api/capabilities)
- rontend/client.py (get_capabilities())
- rontend/app.py (dynamic supported_types & category branching)
- ackend/tests/test_frontend_smoke.py

---

## Decision: Phase 12 — Audio Processor & Honest Degraded Mode (Branch B)

**Date:** 2026-09-27

**Decision:**
Implement `AudioProcessor` conforming to the `FileProcessor` interface. Because FFmpeg binary is absent on the host system (`shutil.which("ffmpeg") is None`), activate **Branch B (Degraded Mode)**:
1. Provide robust, pure-Python metadata extraction for audio formats (`.wav`, `.mp3`) using `mutagen` and Python standard library `wave`.
2. Honestly declare audio capabilities in `capabilities.json`: supported for `extract_metadata`, while documenting `"manipulation": "trim/convert/compress not available — FFmpeg required"`.
3. Raise explicit, structured `ExecutionError` when audio manipulation (e.g. trim, compress, convert) is requested in the absence of FFmpeg. Never crash, never silent no-op, never fake success.
4. Record missing binary in `MANUAL_ACTIONS_LOG.md` per protocol.
5. In the frontend, render metadata (duration, sample rate, channels), audio playback widget (`st.audio`), and honest degradation warning.
6. Extend `backend/tests/test_frontend_smoke.py` with `test_audio_metadata_only_mode_is_honest` using Streamlit `AppTest` to verify the end-to-end user experience.

**Context:**
Audio and video manipulation typically require external FFmpeg binaries. When such binaries are not pre-installed in the environment, the application must maintain absolute architectural honesty: partially supported formats must work for feasible operations (metadata profiling) while gracefully and informatively rejecting manipulation tasks.

**Why Pure-Python Metadata:**
`mutagen` and `wave` extract sample rate, channels, bit rate, sample width, and exact duration without external system dependencies.

**Verification:**
- Verified synthetic fixture `tests/fixtures/audio/sample.wav` (44.1 kHz, 16-bit PCM stereo, 3.0s duration) against `expected_values.json`.
- All 7 tests in `backend/tests/test_frontend_smoke.py` pass cleanly.
- Full 272-test suite passes with zero regressions.

---

## Decision: Phase 12 — Video Processor & Honest Degraded Mode (Branch B)

**Date:** 2026-09-27

**Decision:**
Implement `VideoProcessor` conforming to the `FileProcessor` interface under **Branch B (Degraded Mode)**:
1. **FFmpeg Attempt:** Actually attempted installation via `winget install Gyan.FFmpeg`. Windows package manager installed Gyan.FFmpeg 9.0.2 full build zip, extracted binaries, and modified the user PATH environment variable. However, because running shells/subprocesses require a full environment restart to inherit updated system paths, `shutil.which("ffmpeg")` returns `None` within the active session. Therefore, Branch B governs both Audio and Video in this session.
2. **File Detection:** Added real magic-byte sniffers in `backend/core/file_detection.py` for MP4 (`ftyp`/`moov` box signatures), MOV (`ftypqt`), AVI (`RIFF....AVI `), MKV (`\x1a\x45\xdf\xa3` EBML header), and WEBM (`\x1a\x45\xdf\xa3` EBML header). Hand-crafted minimal header-only fixtures created in `tests/fixtures/video/` and verified with `backend/tests/test_video_detection.py`.
3. **Pure-Python Container Profiling:** Because reliable video stream decoding (frame rate, resolution, duration, codec) across arbitrary containers is fragile without FFmpeg, `VideoProcessor.profile()` returns verified container-level metadata (file size, detected container format) and explicitly notes that stream decoding requires FFmpeg.
4. **Structured Manipulation Error:** Every video manipulation operation (`trim`, `extract_frame`, `resize`, `convert_format`, `compress`, `extract_audio`) checks `is_ffmpeg_available()`. If False, it immediately raises a structured `ExecutionError("trim/extract_frame/resize/convert/compress not available — FFmpeg required")`. Never crash, never silent no-op, never fake success.
5. **Processor Registry & Schemas:** Registered `VideoProcessor` in `ProcessorRegistry` for `FileCategory.VIDEO`. Supported extensions added to `SUPPORTED_EXTENSIONS` and route regexes.
6. **Platform Honesty:** Updated `capabilities.json` and `MANUAL_ACTIONS_LOG.md` to reflect container detection and file size support while documenting FFmpeg requirement for manipulation.
7. **Frontend Integration:** Dynamic uploader accepts video formats (`.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`), displays `VIDEO` category badge, container info, and warning on manipulation attempts.
8. **Automated Verification:** Verified across 7 unit tests in `backend/tests/test_video_detection.py`, 7 unit tests in `backend/tests/test_video_processor.py`, and AppTest smoke coverage in `backend/tests/test_frontend_smoke.py`.

---

## Decision: Phase 12 — Superseding Branch B with Branch A via Path-Independent FFmpeg Discovery

**Date:** 2026-09-27

**Decision:**
Formally supersede the earlier Branch B (Degraded Mode) decisions for both Audio and Video processors. Promote both processors to **Branch A (Full Manipulation & Metadata Capabilities)** powered by a newly implemented, path-independent discovery strategy:
1. **Diagnosis & Reversal of Premature Branch B Conclusion:**
   - Package `Gyan.FFmpeg` 9.0.2 was indeed successfully installed on disk to:
     `%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin`
   - Registry examination (`HKEY_CURRENT_USER\Environment\Path`) confirmed the directory was recorded in the Windows user environment.
   - However, running parent processes and child shells on Windows do not inherit updated registry environment variables without a full process/session restart. Conflating this operating system inheritance barrier with binary absence was an architectural error.
2. **Path-Independent Resolution Architecture (`backend/core/ffmpeg_locator.py`):**
   - Implemented a 3-tier resolution strategy:
     - Tier 1: Standard system PATH lookup (`shutil.which("ffmpeg")`, `shutil.which("ffprobe")`)
     - Tier 2: Explicit operator overrides (`FFMPEG_BINARY`, `FFPROBE_BINARY`)
     - Tier 3: Glob discovery of the known WinGet portable package directory on Windows (`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\**\bin\ffmpeg.exe`) and direct User Registry probe.
   - Both binaries (`ffmpeg.exe -version` and `ffprobe.exe -version`) verified functional and callable.
3. **Full Branch A Implementations:**
   - **AudioProcessor:** Implements `extract_metadata`, `trim`, `convert_format`, and `compress`. Outputs verified via mutagen and standard library `wave`.
   - **VideoProcessor:** Implements `extract_metadata` (via `ffprobe`), `trim`, `extract_frame` (via Pillow verification), `resize`, `convert_format`, `compress`, and `extract_audio`.
   - **Real Media Fixtures:** Hand-crafted stubs replaced with 100% real synthetic media generated via FFmpeg (`testsrc=duration=3:size=320x240:rate=24`, `sine=frequency=1000:duration=3`).
   - **Validation Contract:** Non-vacuous `validate_output()` executes tolerance-bounded duration comparisons (`abs(actual - expected) < 0.1s`), Pillow dimension verification, and container format checks.
4. **Platform Alignment:**
   - Updated `capabilities.json` and `MANUAL_ACTIONS_LOG.md` to reflect full Branch A support with FFmpeg status marked RESOLVED.
   - Frontend UI (`frontend/app.py`) updated to render live `st.audio` and `st.video` widgets with real stream metrics.
   - AppTest smoke tests (`backend/tests/test_frontend_smoke.py`) updated from degraded-mode warnings to asserting real manipulation execution.
   - Full regression suite passes at 290 tests with zero regressions.

---

## Decision: Phase 13 — Archive Security Architecture (Zip-Slip, Bomb Guard, Sandboxed Extraction)

**Date:** 2026-09-27

**Decision:**
Implement a dedicated, zero-dependency `ArchiveSecurityGuard` in `backend/core/archive_security.py` that strictly validates all incoming archives (ZIP, TAR, GZ) prior to any extraction:
1. **Zip-Slip Traversal Prevention:**
   - Detects and rejects any entry containing directory traversal elements (`..`), absolute path markers (`/` or `C:\`), or whose canonical resolved destination falls outside the target extraction workspace.
   - Raises `ArchiveSecurityError(FileValidationError)` with precise, actionable violation reasons.
2. **Archive-Bomb Declared Size Check:**
   - Inspects entry headers and central directories *before* writing bytes to disk.
   - Rejects any archive declaring total uncompressed size exceeding `MAX_UNCOMPRESSED_BYTES` (500 MB).
   - Rejects any archive exceeding `MAX_ARCHIVE_ENTRIES` (10,000 files).
3. **Session-Isolated Sandboxed Extraction:**
   - All extractions occur inside isolated per-session workspaces: `backend/data/sessions/<session_id>/archive_workspace/<uuid>/`.
   - Guaranteed cleanup via context manager `SafeArchiveWorkspace` and robust `finally` blocks, ensuring no orphaned temporary files remain upon either success or error.
4. **Pure Standard Library Implementation:**
   - Uses exclusively `zipfile`, `tarfile`, and `gzip` from the Python standard library. No new third-party dependencies.

**Why This Approach:**
Archive extraction is a high-risk vector for remote code execution, file overwrite attacks, and denial of service. Enforcing the security guard at both entry inspection and extraction stages guarantees system safety.

---

## Decision: Phase 13 — Explicit Deferral of 7Z Format

**Date:** 2026-09-27

**Decision:**
Explicitly defer support for the 7Z archive format rather than introducing `py7zr` as a new dependency. Record `"7z": "Deferred - requires py7zr external dependency"` in `capabilities.json`.

**Context & Rationale:**
In accordance with `techstack.md`'s foundational principle ("avoid unnecessary dependencies"), standard library `zipfile`, `tarfile`, and `gzip` cover >99% of archive use cases in enterprise data workflows. Adding `py7zr` would expand dependency footprint and attack surface without immediate demand. Deferral is marked honestly and transparently in platform capabilities.

---

## Decision: Phase 13 — Universal Multi-File / Batch Processing Pipeline and Honest Partial Success

**Date:** 2026-09-27

**Decision:**
Implement universal multi-file and batch processing across all existing format processors (tabular, document, image, audio, video, archive):
1. **API & Ingestion:**
   - Updated `POST /api/pipeline/run` to accept `files: list[UploadFile] = File(None)` alongside single `file: UploadFile | None = None`.
   - Updated frontend uploader with `accept_multiple_files=True` and dynamic capability integration.
2. **Execution Flow (`DataWisePipeline.run_batch`):**
   - Ingests multiple files into a shared batch session workspace.
   - Inspects each file independently using magic-byte sniffing (`detect_file_category`).
   - Routes each file to its corresponding domain processor according to the user's intent.
3. **Honest Partial-Success Semantics:**
   - In heterogeneous batches (e.g. 2 CSVs and 1 JPG submitted with a tabular cleaning prompt), files matching the target domain are processed; inapplicable files are marked `excluded` with clear explanations.
   - The batch status is honestly declared as `success` (if all succeeded) or `partial_success` (if some were excluded or failed).
   - Generates structured `BatchSummary` (`total_files`, `succeeded_count`, `failed_count`, `excluded_count`) and per-file `BatchItemResult` audit trails.
4. **Safe Output Consolidation:**
   - When multiple files are processed, outputs are automatically packaged into a safe, single `result.zip` for download, alongside rich UI cards, metrics, and data preview.

---

## Decision: Phase 14 — LLM-Backed Structured Planning with Multi-Provider Adapter & Zero-Hallucination Tool Catalog

**Date:** 2026-10-24

**Decision:**
Implement a lightweight, dependency-free multi-provider LLM adapter (`backend/core/llm_provider.py`) supporting Google Gemini (`gemini-2.0-flash`), Anthropic Claude (`claude-3-5-sonnet`), OpenAI (`gpt-4o-mini`), and local OpenAI-compatible endpoints (Ollama/vLLM), directly integrated into Stage 2 (Intent Understanding) and Stage 3 (Task Planning and Revision):
1. **Lightweight Native REST Implementation:**
   - Built with standard library `urllib.request` and `json` to eliminate external dependency bloat.
   - Enforces strict JSON Schema extraction and Pydantic v2 runtime validation.
2. **Metadata-Only DataProfile Privacy Guarantee:**
   - Only structural metadata (columns, types, null counts, duplicate counts, row count) is transmitted to LLMs — strictly zero raw records or cell values are ever transmitted.
3. **Zero-Hallucination Tool Catalog Verification:**
   - LLMs plan using an explicit manifest of vetted, registered tool functions (`backend/core/executor.py`).
   - Any hallucinated or unregistered tool names generated by models are proactively rejected during plan compilation.
4. **Resilient Deterministic Heuristic Fallback:**
   - If no API key is provided, or if network timeouts / rate limits occur, the pipeline seamlessly and transparently falls back to the deterministic heuristic planner without crashing or failing.
5. **Validation-Guided Plan Revision:**
   - When execution fails post-validation sanity assertions, `ValidationResult` diagnostic details are provided to the LLM revision engine to intelligently correct failed step parameters.




