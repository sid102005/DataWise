# DataWise — In-Depth Project Overview

A deep walkthrough of what DataWise is, how the pieces fit together, and how a request travels from upload to download. Use this to build a solid mental model of the codebase.

For install and run commands, see [`PROJECT_SETUP.md`](PROJECT_SETUP.md).

---

## 1. What DataWise is (in one paragraph)

**DataWise** is a local, multi-format data processing agent. You upload one or more files and write a plain-English instruction. The system detects the real file type, profiles the content, turns your words into an ordered plan, runs that plan with **deterministic libraries** (pandas, Pillow, FFmpeg, etc.—not LLM-generated code), validates the result, and shows artifacts plus an audit trail in a Streamlit UI.

Core design rule:

> **Reasoning plans and coordinates; deterministic code executes all data operations.**

That split keeps math and transforms reviewable, avoids “hallucinated” calculations, and keeps data on your machine by default.

---

## 2. The problem it solves

Data work is split across tools:

| Kind of data | Typical tools people juggle |
| :--- | :--- |
| CSV / Excel / JSON | pandas, SQL, spreadsheet formulas |
| PDF / DOCX / text | PyMuPDF, Word parsers, custom scripts |
| Images | Photoshop, Pillow, ImageMagick |
| Audio / video | Audacity, HandBrake, FFmpeg CLI |
| ZIP / TAR / GZ | Extract → route manually → re-zip (and risk Zip-Slip / bombs) |

DataWise collapses that into **one upload + one prompt**, with session sandboxes and security guards for archives.

---

## 3. High-level architecture

```text
┌─────────────────────────────────────┐
│  Streamlit UI  (frontend/app.py)    │  port 8501
│  upload · prompt · preview · tabs   │
└─────────────────┬───────────────────┘
                  │ HTTP (DATAWISE_API_URL)
                  ▼
┌─────────────────────────────────────┐
│  FastAPI  (backend/main.py)         │  port 8000, workers=1
│  /api/pipeline/run · /download · …  │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│  DataWisePipeline                   │
│  (backend/core/pipeline.py)         │
│  stages: ingest → detect → profile  │
│          → intent → plan → execute  │
│          → validate → export        │
└─────────────────┬───────────────────┘
                  │
        ┌─────────┴──────────┐
        ▼                    ▼
 ProcessorRegistry      Tabular tools
 (format handlers)      (clean/transform/…)
```

**UI never touches files directly for processing.** It posts to the API; the API owns sessions under `workspace/sessions/{uuid}/`.

---

## 4. Mental model: the 6-stage pipeline

Every successful run roughly follows this loop (batch runs the same loop per file, then packages outputs):

```text
Upload + prompt
    │
    ▼
① Input & security          → whitelist extension, create session folder
    │
    ▼
①.5 Magic-byte detection    → true type (not just .csv / .jpg name)
    │
    ▼
①b Profiling                → schema / dimensions / codecs / archive list
    │
    ▼
② Intent parsing            → discrete objectives from the prompt
    │
    ▼
③ Planning                  → ordered steps mapped to known tools/ops
    │                         (may short-circuit: NEEDS_CLARIFICATION)
    ▼
④ Execution                 → pandas / Pillow / FFmpeg / zipfile / …
    │
    ▼
⑤ Validation                → existence, size, domain checks; retry ≤ 2
    │
    ▼
⑥ Delivery                  → export + summary + preview + download URL
```

Retries: the pipeline allows up to **3 attempts** (`MAX_RETRIES = 2`) when validation fails, revising/retrying rather than silently accepting bad output.

---

## 5. Repository map (what lives where)

```text
DataWise/
├── frontend/           # Streamlit app + HTTP client
├── backend/
│   ├── main.py         # FastAPI app entry
│   ├── config.py       # paths, supported extensions
│   ├── api/routes.py   # REST endpoints
│   ├── core/           # pipeline stages + security + FFmpeg locator
│   ├── processors/     # one handler per file category
│   ├── tools/          # pure tabular operations (allow-listed)
│   ├── models/         # Pydantic schemas (contracts)
│   └── tests/          # pytest suite
├── scripts/            # fixture generators / verification helpers
├── tests/fixtures/     # canonical sample files + expected values
├── test_data/          # demo CSVs
├── workspace/          # runtime sessions (gitignored contents)
├── capabilities.json   # machine-readable feature flags
└── docs / PRD / flow…  # product & design notes
```

### Frontend (`frontend/`)

| File | Role |
| :--- | :--- |
| `app.py` | Main UI: uploader, prompt, Run button, result tabs |
| `client.py` | `call_pipeline`, `fetch_file`, `get_capabilities` |
| `helpers.py` | Parse API results; redact paths/traces for display |

### Backend core (`backend/core/`)

| Module | Role |
| :--- | :--- |
| `pipeline.py` | Orchestrator for single-file and batch runs |
| `input_manager.py` | Validate upload; save as `input{ext}` in session dir |
| `file_detection.py` | Magic-byte sniff → `FileCategory` |
| `understanding.py` | Tabular schema / type inference helpers |
| `intent.py` | Prompt → objectives (keyword / regex heuristics today) |
| `planner.py` | Objectives → ordered `Plan` / `Step` list |
| `executor.py` | Runs **allow-listed** tabular tools only |
| `validator.py` | Post-exec sanity + operation-specific checks |
| `output.py` | Export files, previews, plain-English summary |
| `archive_security.py` | Zip-Slip + bomb limits before extract |
| `ffmpeg_locator.py` | Find `ffmpeg` / `ffprobe` on PATH / env / WinGet |
| `exceptions.py` | Domain error types |

### Processors (`backend/processors/`)

All implement a shared contract (`base.py`): `profile` → `validate_input` → `execute` → `validate_output` → `export` → `cleanup`.

Registered categories:

| Category | Module | Typical extensions |
| :--- | :--- | :--- |
| Tabular | `tabular.py` | `.csv`, `.xlsx`, `.json` |
| Document | `document.py` | `.pdf`, `.docx`, `.txt`, `.md` |
| Image | `image.py` | `.jpg`, `.png`, `.webp`, … |
| Audio | `audio.py` | `.mp3`, `.wav` |
| Video | `video.py` | `.mp4`, `.mov`, `.mkv`, … |
| Archive | `archive.py` | `.zip`, `.tar`, `.gz`, `.tgz` |

`registry.py` maps category → processor so the pipeline stays format-agnostic: detect → look up → call.

### Tabular tools (`backend/tools/`)

These are pure functions the executor may call—nothing outside the allow-list runs for tabular transforms:

| Area | Examples |
| :--- | :--- |
| Clean | `drop_duplicates`, `handle_missing`, `fix_type_mismatches`, `standardize_dates` |
| Transform | `drop_column`, `add_column`, `rename_columns`, `filter_rows`, `add_derived_column` |
| Aggregate | `groupby_aggregate`, `sort_values`, `top_n` |
| Chart | `bar_chart`, `line_chart`, `pie_chart` (matplotlib → PNG) |

Non-tabular ops (resize image, trim audio, extract PDF text, …) live **inside** the matching processor, not in `backend/tools/`.

---

## 6. End-to-end request walkthrough

### Single file (example: CSV)

1. User uploads `sales.csv` and types:  
   `clean missing values, drop duplicates, and make a bar chart of revenue by region`
2. Streamlit (`client.py`) `POST`s multipart form data to `/api/pipeline/run`.
3. `InputManager` creates `workspace/sessions/<uuid>/`, stores file as `input.csv` (original name kept as metadata; path traversal stripped).
4. `detect_file` reads magic bytes → category `tabular`.
5. `TabularProcessor.profile` (via understanding helpers) builds a `DataProfile`: columns, dtypes, null ratios, row count, etc.
6. `parse_intent` turns the sentence into objectives like `clean`, `visualize`.
7. `build_plan` emits ordered steps: handle_missing → drop_duplicates → groupby → bar_chart.
8. `execute_plan` runs each tool on a DataFrame in memory / session intermediates.
9. `validate` checks outputs (e.g. file exists, chart produced, row sanity).
10. `output` exports CSV/XLSX/JSON as requested, builds preview + summary.
11. API returns `PipelineOutput`; UI shows metrics, tabs (Preview, Charts, Plan, Validation, Downloads).

### Image / audio / video

Same skeleton, different executor path:

- Image → Pillow ops (`resize`, `crop`, `rotate`, …)
- Audio / video → FFmpeg subprocesses + mutagen/ffprobe for metadata
- Validation uses domain rules (exact dimensions; duration ± tolerance)

### Archives

1. Pre-scan with `archive_security` (reject `../` paths, >500 MB uncompressed, >10k entries, extreme compression ratios).
2. List / extract members into the session sandbox.
3. Route each member through detection + its processor when the prompt asks to process contents.
4. Optionally repackage into `result.zip`.

### Batch (multiple uploads)

`DataWisePipeline.run_batch`:

- Processes each file independently (own routing).
- Aggregates per-item success/failure (`BatchItemResult`, `BatchSummary`).
- Can return **partial success** and a consolidated download ZIP.

---

## 7. Intent & planning (important nuance)

Product docs (`flow.md`, PRD) describe an **LLM planning** future. **Today’s default path is heuristic:**

- `intent.py` / `planner.py` use keywords and patterns.
- No cloud call is required.
- Unclear prompts → `NEEDS_CLARIFICATION` (UI asks a follow-up) or a parse failure.
- Env keys (`ANTHROPIC_API_KEY`, etc.) are reserved stubs for later vision/LLM work.

So when you read “LLM plans, code executes,” treat that as the **architecture rule** and the **target design**. The shipping MVP already enforces “code executes”; planning is rule-based until LLM integration lands.

---

## 8. API surface (what the UI talks to)

Defined mainly in `backend/api/routes.py`:

| Concern | Typical endpoint | Notes |
| :--- | :--- | :--- |
| Run pipeline | `POST /api/pipeline/run` | File(s) + prompt (+ optional export format) |
| Capabilities | `GET /api/capabilities` | Merges `capabilities.json` with registered processors |
| Download | session-scoped download routes | UUID checks; reject `../`, `/`, `\` in names |
| Health | `GET /health` | Liveness |
| Docs | `/docs` | Swagger UI |

CORS is open (`*`) for local Streamlit. Downloads are confined to the owning session directory.

---

## 9. Data contracts (Pydantic)

`backend/models/schemas.py` is the shared language between stages. Important shapes:

| Model | Meaning |
| :--- | :--- |
| `DataProfile` | What we know about the input (tabular + media fields) |
| `Objective` | Parsed goal (clean / transform / visualize / extract / …) |
| `Step` / `Plan` | Ordered, tool-mapped execution list |
| `ExecutionResult` | What a step produced |
| `ValidationResult` | Pass/fail + check details |
| `PipelineOutput` | Final payload to the UI (status, summary, preview, URLs, batch fields) |
| `ClarificationRequest` | Ambiguity short-circuit |
| `ErrorResponse` | Sanitized client-facing errors |

Statuses include: `success`, `partial_success`, `needs_clarification`, `failed`.

Understanding these models is the fastest way to read pipeline code without getting lost in implementation detail.

---

## 10. Security & privacy model

Designed for **local-first** use:

| Guard | What it does |
| :--- | :--- |
| Session isolation | Each run gets `workspace/sessions/{uuid}/` |
| Extension whitelist | Only `SUPPORTED_EXTENSIONS` in `config.py` |
| Magic-byte detection | Extension spoofing doesn’t control routing alone |
| Zip-Slip defense | Canonical path must stay under extract root |
| Archive bombs | Caps on uncompressed size (500 MB), entry count (10k), ratio |
| Image bombs | Pillow `MAX_IMAGE_PIXELS` style limits (~100M pixels) |
| Excel size | Cell count cap (~5 million) in input manager |
| Download hardening | Session UUID regex + filename sanitization |
| Error redaction | No raw stack traces / absolute paths in UI messages |

Default: **no user data uploaded to cloud APIs**. Planned LLM modes are meant to send **metadata only** (headers, dtypes, dimensions)—not raw rows—when enabled.

---

## 11. Supported formats & capability flags

Authoritative machine list: [`capabilities.json`](capabilities.json). Human ops list: [`DATAWISE_CAPABILITIES.md`](DATAWISE_CAPABILITIES.md).

| Processor | Status | Notable ops | Limitations |
| :--- | :--- | :--- | :--- |
| Tabular | On | Clean, transform, aggregate, charts | — |
| Document | On | Text/tables extract, word counts | OCR off; no summarization; legacy `.doc` rejected |
| Image | On | Resize, crop, rotate, convert, compress, metadata | OCR / vision deferred |
| Audio | On | Metadata, trim, convert, compress | Transcription deferred |
| Video | On | Metadata, trim, frame, resize, convert, extract audio | Complex effects deferred |
| Archive | On | Profile, list, extract+process | `.7z` deferred |
| Presentation | Off | — | Phase 14 (`.pptx`) |

---

## 12. UI experience (what you see)

Streamlit app flow:

1. Upload one or many supported files.
2. Enter a natural-language prompt.
3. For tabular, optionally pick export format (CSV / Excel / JSON).
4. **Run Pipeline**.
5. Inspect:
   - Metrics (shape, time, checks)
   - Plain-English summary
   - **Preview** (table / image / audio / video / text)
   - **Charts** (if generated)
   - **Plan** (steps that ran)
   - **Validation** (assertions)
   - **Downloads**

Capabilities loaded from the API drive which extensions the uploader advertises.

---

## 13. Testing strategy (how confidence is built)

Tests live under `backend/tests/` (configured in `pytest.ini`):

| Layer | What it covers |
| :--- | :--- |
| Unit | Tools, schemas, detection, individual processors |
| Integration | API routes, e2e scenarios, batch |
| Security | Path traversal, zip bombs, prompt injection, session isolation, LLM call budget |
| Frontend | Helper unit tests + Streamlit `AppTest` smoke |

Fixtures under `tests/fixtures/` (documents, images, audio, video, archives, batch) plus generators in `scripts/` keep expected outputs reproducible.

---

## 14. Development phases (why the code looks layered)

The repo was built in numbered phases (see README verification table). Rough story:

1. Contracts & health  
2. Input / sessions  
3. Understanding (tabular profile)  
4. Intent + planner  
5. Executor + tabular tools  
6. Validator  
7. Streamlit UI  
8. Adversarial hardening  
9. Universal detection + registry  
10–12. Document / image / audio-video processors  
13. Archives + batch  
14. (Planned) presentations  

That history explains the clean split: **tabular tools first**, then a **processor registry** so new formats plug in without rewriting the pipeline loop.

---

## 15. How to read the code efficiently

Suggested order for learning:

1. `backend/models/schemas.py` — vocabulary  
2. `backend/core/pipeline.py` — control flow  
3. `backend/processors/base.py` + `registry.py` — extension point  
4. One processor you care about (`tabular.py` or `image.py`)  
5. `backend/api/routes.py` + `frontend/client.py` — boundary  
6. `frontend/app.py` — how results are shown  

When debugging a failed run, check in order: session folder contents → plan steps in the response → validation messages → processor/tool logs.

---

## 16. Limitations to keep in mind

1. **Heuristic prompts** — colloquial or ambiguous language may need clarification or clearer keywords (`EXAMPLE_COMMANDS.md`).  
2. **OCR / transcription / vision** — not on by default; need extra binaries or API keys later.  
3. **Single worker** — in-memory sessions; no multi-worker scale-out without Redis (or similar).  
4. **No product CLI** — entry points are uvicorn + Streamlit (plus pytest/scripts).  
5. **No Docker** in-repo despite older design notes mentioning containers.  
6. **Resource limits** — still bound by host RAM/disk for huge media/datasets.

---

## 17. Glossary

| Term | Meaning |
| :--- | :--- |
| **Session** | Isolated UUID folder for one pipeline run’s inputs/outputs |
| **Profile** | Structured metadata about an input before planning |
| **Objective** | Parsed user goal (e.g. clean, visualize) |
| **Plan / Step** | Ordered list of concrete tool/ops to run |
| **Processor** | Format-specific engine implementing the FileProcessor contract |
| **Tool** | Allow-listed tabular pure function |
| **PipelineOutput** | Final API/UI contract for a completed (or clarified/failed) run |
| **Capabilities** | Declared supported ops (`capabilities.json` + live registry) |

---

## 18. Related reading

| Document | Contents |
| :--- | :--- |
| [`PROJECT_SETUP.md`](PROJECT_SETUP.md) | Install, env, run, test, troubleshooting |
| [`README.md`](README.md) | Full product README + examples |
| [`flow.md`](flow.md) | Control-flow diagrams (includes LLM-oriented target wording) |
| [`techstack.md`](techstack.md) | Stack rationale |
| [`PRD.md`](PRD.md) / [`PRD_V2_ADDENDUM.md`](PRD_V2_ADDENDUM.md) | Product requirements |
| [`EXAMPLE_COMMANDS.md`](EXAMPLE_COMMANDS.md) | Tested prompts |
| [`decision.md`](decision.md) | Engineering decisions |
| [`execution.md`](execution.md) | Runtime call-chain notes |

---

*Last aligned with the current codebase layout: FastAPI + Streamlit, six processors, heuristic intent, local-first execution.*
