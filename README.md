# DataWise

> An autonomous, format-agnostic data processing agent that understands natural-language instructions, profiles arbitrary file inputs, plans deterministic execution pipelines, and delivers verified results through an interactive web interface.

---

## 1. Overview

**DataWise** is an intelligent, multi-format data processing and analysis agent designed to bridge the gap between non-technical users and technical data manipulation workflows. 

Instead of requiring users to master diverse tools, command-line utilities, Python libraries, or complex formula syntax, DataWise provides a unified interface: **upload your data and describe what you want in plain English**. DataWise automatically determines the underlying file type, extracts structural metadata, translates instructions into an ordered execution plan, dispatches operations to specialized deterministic processors, verifies the integrity of the results, and surfaces the processed output alongside complete audit trails.

DataWise strictly adheres to a core architectural principle: **The reasoning layer plans and coordinates, but deterministic, testable code executes operations on data.** This design guarantees precision, prevents mathematical hallucinations, ensures verifiable transformations, and maintains complete privacy.

---

## 2. Problem Statement

Modern data workflows are fragmented across incompatible formats, tools, and technical requirements:

* **Tabular Datasets** (`.csv`, `.xlsx`, `.json`) require knowledge of SQL, pandas, or spreadsheet formulas for filtering, cleaning, deduplication, and aggregation.
* **Unstructured Documents** (`.pdf`, `.docx`, `.txt`, `.md`) require specialized parsers, text extraction libraries, or table extractors to normalize and analyze text.
* **Multimedia Assets** (`.jpg`, `.png`, `.wav`, `.mp3`, `.mp4`) require disparate tooling (e.g., Pillow, FFmpeg, Mutagen) for routine operations such as resizing, cropping, audio/video trimming, format conversion, and stream inspection.
* **Bundled Archives** (`.zip`, `.tar`, `.gz`) introduce security hazards (such as Zip-Slip path traversal or archive bombs) and require manual extraction and routing before processing.

Traditional software forces users to manually select and configure the correct application for each file type. DataWise addresses this fragmentation by introducing an **autonomous pipeline architecture** that accepts heterogeneous formats through a single entry point, isolates processing in secure session sandboxes, and executes operations with zero manual configuration.

---

## 3. Objectives

* **Unified Ingestion:** Accept tabular data, documents, images, audio, video, and archives through a single, consistent API and web interface.
* **Format-Agnostic File Detection:** Identify incoming files using binary magic bytes rather than trusting spoofable file extensions.
* **Automated Data Profiling:** Extract structural metadata (dimensions, schemas, audio bitrates, video codecs, archive members) prior to planning.
* **Natural-Language Planning:** Translate user requests into structured, discrete objectives and deterministic execution steps.
* **Deterministic Execution:** Execute all transformations, math, and filtering via vetted Python libraries and binaries (pandas, Pillow, FFmpeg) rather than generative code synthesis.
* **Self-Checking Validation:** Automatically verify generated outputs against pre-execution criteria (e.g., row count sanity, tolerance-bounded duration checks, dimension checks).
* **Security & Sandboxing:** Guard against path traversal attacks (Zip-Slip), decompression bombs, memory exhaustion, and sensitive information leakage.
* **Multi-File Batch Operations:** Support concurrent multi-file uploads with cross-category routing and consolidated archive packaging.

---

## 4. Key Features

* ✅ **Magic-Byte Format Detection**  
  Inspects binary file signatures (magic bytes) to correctly identify incoming data types even when files are mislabeled or extensionless.
* ✅ **Automated Metadata Profiling**  
  Extracts comprehensive metadata before processing: null ratios and column dtypes for tabular data; word counts and table structures for documents; EXIF and dimensions for images; durations, sample rates, and codecs for audio/video; and member manifests for archives.
* ✅ **Deterministic Tool-Mapped Planning**  
  Translates user prompts into an ordered sequence of discrete operations mapped directly to pure Python functions.
* ✅ **Tabular Data Transformation & Analysis**  
  Cleans missing values, deduplicates rows, adds computed columns, filters records, calculates group-by aggregations, and generates bar, line, or pie charts.
* ✅ **Document Parsing & Extraction**  
  Extracts normalized text, paragraphs, headings, and tabular structures from PDF, Word (`.docx`), Markdown, and plain text files.
* ✅ **Image Manipulation & Optimization**  
  Resizes images to exact dimensions, crops bounding boxes, applies lossy compression with quality tuning, rotates images by 90/180/270 degrees, and converts formats across JPEG, PNG, WEBP, GIF, BMP, and TIFF.
* ✅ **Audio & Video Processing (FFmpeg Integration)**  
  Performs tolerance-bounded trimming, stream re-encoding, bitrate compression, video resizing, frame extraction at target timestamps, and audio isolation from video containers.
* ✅ **Archive Processing & Zip-Slip Defense**  
  Inspects, profiles, and safely unpacks ZIP, TAR, and GZ archives with strict canonical path traversal validation and uncompressed volume caps.
* ✅ **Heterogeneous Batch Processing**  
  Ingests multiple files simultaneously, routes each item to its appropriate domain processor, reports honest partial success metrics, and packages outputs into a single download archive.
* ✅ **High-Density Streamlit UI**  
  Provides interactive data previews, embedded media players (audio/video/images), plan inspection logs, validation status monitors, and single-click artifact downloads.
* ✅ **Session Isolation & Error Redaction**  
  Isolates every pipeline run within a unique UUID session directory in `workspace/sessions/` and sanitizes error responses to prevent internal server path leakage.

---

## 5. Supported Data Formats

The following matrix documents the verified capabilities of the DataWise processor registry:

| Category | File Extension | Processor Module | Implementation Status | Verified Operations |
| :--- | :--- | :--- | :--- | :--- |
| **Tabular** | `.csv`, `.xlsx`, `.json` | `TabularProcessor` | ✅ Verified | Cleaning, missing-value imputation, deduplication, column transformations, group-by aggregation, sorting, charting (bar/line/pie). |
| **Document** | `.pdf`, `.docx`, `.txt`, `.md` | `DocumentProcessor` | ✅ Verified | Text extraction, table extraction, word/heading profiling, format normalization. *(OCR disabled pending local Tesseract binary).* |
| **Image** | `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tiff` | `ImageProcessor` | ✅ Verified | Exact resizing, bounding-box cropping, 90°/180°/270° rotation, format conversion, quality compression, metadata extraction. |
| **Audio** | `.wav`, `.mp3` | `AudioProcessor` | ✅ Verified | Metadata profiling (sample rate, channels, duration), trimming, format conversion (WAV/MP3), bitrate compression, native playback. |
| **Video** | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` | `VideoProcessor` | ✅ Verified | Stream profiling (resolution, framerate, codecs), trimming, frame capture to PNG, resizing, audio track extraction, native playback. |
| **Archive** | `.zip`, `.tar`, `.gz`, `.tgz` | `ArchiveProcessor` | ✅ Verified | Pre-extraction security inspection (Zip-Slip defense, 500 MB volume cap), member listing, recursive domain processing, repackaging. |
| **Multi-File Batch** | Any supported formats | `DataWisePipeline` | ✅ Verified | Multi-file ingestion, magic-byte routing, parallel item processing, partial success reporting, consolidated ZIP export. |
| **Presentation** | `.pptx` | Planned | ⏳ Deferred (Phase 14) | Slide text extraction, table extraction, and slide thumbnail rendering planned for Phase 14. |
| **Archive (7Z)** | `.7z` | Deferred | ⚠️ Not Implemented | Deferred to avoid external non-standard dependencies (`py7zr`). |
| **Legacy Word** | `.doc`, `.docm` | Rejected | ❌ Unsupported | Binary and macro-enabled legacy formats are detected and rejected for security. |

---

## 6. How DataWise Works

DataWise executes operations using a linear, self-checking pipeline loop:

```text
User File Upload + Prompt
           │
           ▼
Stage 1: Input & Security Guard
  • Verify file extension against whitelist
  • Validate declared archive safety (Zip-Slip & size caps)
  • Assign isolated session UUID in workspace/sessions/{uuid}/
           │
           ▼
Stage 1.5: Binary Magic-Byte Detection
  • Sniff true file signatures (RIFF, PK, ID3, PNG, PDF, etc.)
  • Route to registered domain processor via ProcessorRegistry
           │
           ▼
Stage 1b: In-Memory Metadata Profiling
  • Profile schema, dimensions, stream properties, or manifests
  • Enforce decompression-bomb guards (Image.MAX_IMAGE_PIXELS)
           │
           ▼
Stage 2 & 3: Intent Parsing & Task Planning
  • Parse natural-language prompt into discrete operational objectives
  • Map objectives to verified Python functions (tools) in an ordered step list
           │
           ▼
Stage 4: Deterministic Tool Execution
  • Execute steps sequentially using domain libraries (pandas, Pillow, FFmpeg)
  • Produce intermediate and target result artifacts
           │
           ▼
Stage 5: Output Validation & Quality Sanity Checks
  • Verify output existence and non-zero byte size
  • Run domain checks (duration tolerance, dimension matching, null reductions)
           │
           ▼
Stage 6: Artifact Delivery & Feedback
  • Package results (CSV, JSON, media file, or consolidated ZIP archive)
  • Return execution telemetry, audit summary, and UI preview
```

---

## 7. Architecture

The system is organized into decoupled layers designed for modularity, testability, and security:

```text
frontend/
  ├── app.py                # Streamlit UI (file uploader, prompt bar, telemetry, tabs)
  ├── client.py             # HTTP client communicating with FastAPI backend
  └── helpers.py            # Result renderers, media players, status cards

backend/
  ├── main.py               # FastAPI entry point, CORS, lifespan session initialization
  ├── config.py             # Global paths, supported extensions, workspace directories
  │
  ├── api/
  │   └── routes.py         # HTTP endpoints: /pipeline/run, /capabilities, /download
  │
  ├── core/
  │   ├── pipeline.py       # Orchestration state machine for single & batch runs
  │   ├── input_manager.py  # Upload validation, session directory provisioning
  │   ├── file_detection.py # Magic-byte signature sniffing & MIME categorization
  │   ├── understanding.py  # Tabular profiling and schema inference
  │   ├── intent.py         # Prompt objective parser
  │   ├── planner.py        # Objective-to-tool step list compiler
  │   ├── executor.py       # Deterministic tool runner
  │   ├── validator.py      # Pre/post execution sanity assertions
  │   ├── output.py         # Export formatting, preview generation, synthesis summaries
  │   ├── archive_security.py # Canonical path traversal & archive bomb guards
  │   └── ffmpeg_locator.py # Path-independent FFmpeg/FFprobe binary resolution
  │
  ├── processors/
  │   ├── base.py           # Abstract BaseProcessor contract (profile, execute, validate, export)
  │   ├── registry.py       # Central dynamic registry mapping categories to processors
  │   ├── tabular.py        # Tabular processor (CSV, Excel, JSON)
  │   ├── document.py       # Document processor (PDF, DOCX, TXT, MD)
  │   ├── image.py          # Image processor (Pillow: resize, crop, rotate, convert, compress)
  │   ├── audio.py          # Audio processor (FFmpeg/Mutagen: metadata, trim, convert, compress)
  │   ├── video.py          # Video processor (FFmpeg/FFprobe: trim, extract frame, resize, audio)
  │   └── archive.py        # Archive processor (zipfile/tarfile recursive processing)
  │
  ├── tools/                # Pure tabular transformation functions (clean, transform, aggregate, chart)
  └── models/schemas.py     # Pydantic v2 schemas for all pipeline inputs, states, and outputs
```

### Component Responsibilities

1. **API Layer (`backend/api/`):** Exposes asynchronous REST endpoints. Validates session UUIDs, enforces file download boundaries to prevent path traversal, and returns structured `PipelineOutput` responses.
2. **Processor Registry (`backend/processors/registry.py`):** Dynamically associates file categories with their respective processing engines, allowing new format handlers to be introduced without modifying the core pipeline loop.
3. **Archive Security Engine (`backend/core/archive_security.py`):** Analyzes archive central directories before extraction to reject malicious entries (e.g., `../../etc/passwd`), uncompressed sizes exceeding 500 MB, or entry counts exceeding 10,000 files.
4. **FFmpeg Locator (`backend/core/ffmpeg_locator.py`):** Discovers multimedia binaries across standard system `PATH`, explicit environment variables (`FFMPEG_BINARY`, `FFPROBE_BINARY`), Windows WinGet portable installations, and registry configurations.

---

## 8. Technology Stack

| Category | Technology | Version / Specification | Justification |
| :--- | :--- | :--- | :--- |
| **Language** | Python | `3.14.7` | Modern runtime with enhanced typing, path handling, and async support. |
| **Backend Framework** | FastAPI | `0.141.1` | High-performance asynchronous API framework with automatic OpenAPI documentation. |
| **ASGI Server** | Uvicorn | `0.53.0` | Lightweight ASGI web server configured with single-worker execution (`workers=1`). |
| **Frontend Framework** | Streamlit | `1.64.0` | Interactive web interface supporting file uploads, media players, and dataframes. |
| **Data Contracts** | Pydantic | `2.13.5` | Strict schema validation, serializing pipeline states, and ensuring contract integrity. |
| **Tabular Data** | Pandas & NumPy | `pandas 3.0.6`, `numpy 2.5.3` | Deterministic, high-throughput tabular manipulation, cleaning, and aggregation. |
| **Spreadsheet I/O** | OpenPyXL | `3.1.5` | Native reading and writing of Excel (`.xlsx`) files. |
| **Document Processing** | PyMuPDF & python-docx | `PyMuPDF 1.25.x`, `python-docx 1.1.x` | Native parsing and extraction for PDF and Microsoft Word documents. |
| **Image Processing** | Pillow (PIL) | `12.3.0` | Comprehensive raster image manipulation, format conversions, and EXIF extraction. |
| **Audio Metadata** | Mutagen | `1.47.0` | Header inspection and audio tag extraction for MP3 and WAV streams. |
| **Multimedia Engine** | FFmpeg & FFprobe | `9.0+` (WinGet / System) | Subprocess-driven media manipulation (trimming, transcoding, frame extraction). |
| **Visualization** | Matplotlib | `3.11.2` | Headless chart generation exported as high-resolution PNG artifacts. |
| **Testing** | Pytest | `9.1.1` | Comprehensive test runner verifying unit, integration, and UI smoke scenarios. |

---

## 9. Project Structure

```text
datawise/
├── .env.example                  # Environment configuration template
├── .gitignore                    # Production Git ignore rules
├── capabilities.json             # Machine-readable registry of verified capabilities
├── DATAWISE_CAPABILITIES.md      # Detailed capabilities and limitations documentation
├── EXAMPLE_COMMANDS.md           # Reference guide of tested, working prompt commands
├── MANUAL_ACTIONS_LOG.md         # Environment setup and external binary tracking log
├── PRD.md                        # Product requirements document (v1 baseline)
├── PRD_V2_ADDENDUM.md            # Product requirements addendum (v2 universal format scope)
├── pytest.ini                    # Pytest test configuration and path settings
├── requirements.txt              # Pinned Python project dependencies
├── techstack.md                  # Architectural decisions and dependency rationale
├── flow.md                       # End-to-end data and control flow specification
├── features.md                   # Feature specifications and acceptance criteria
├── decision.md                   # Engineering decision records (ADRs)
├── execution.md                  # Runtime execution flow and module interaction log
│
├── backend/
│   ├── main.py                   # FastAPI server entry point
│   ├── config.py                 # Paths, extensions, and directory initialization
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py             # REST API routes (/pipeline/run, /capabilities, /download)
│   ├── core/
│   │   ├── archive_security.py   # Zip-Slip and archive bomb security defenses
│   │   ├── exceptions.py         # Custom application exceptions
│   │   ├── executor.py           # Tool execution coordinator
│   │   ├── ffmpeg_locator.py     # System-independent FFmpeg/FFprobe resolution
│   │   ├── file_detection.py     # Binary signature sniffing
│   │   ├── input_manager.py      # Ingestion validation and session creation
│   │   ├── intent.py             # Natural-language objective parser
│   │   ├── output.py             # Export file generator and summary synthesizer
│   │   ├── pipeline.py           # Main orchestration state machine
│   │   ├── planner.py            # Plan compiler and step generator
│   │   ├── understanding.py      # Tabular profiling and schema inference
│   │   └── validator.py          # Assertion and validation layer
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py            # Pydantic v2 data models
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── archive.py            # Archive processor (ZIP, TAR, GZ)
│   │   ├── audio.py              # Audio processor (WAV, MP3)
│   │   ├── base.py               # Abstract BaseProcessor contract
│   │   ├── document.py           # Document processor (PDF, DOCX, TXT, MD)
│   │   ├── image.py              # Image processor (Pillow)
│   │   ├── registry.py           # Central processor registry
│   │   ├── tabular.py            # Tabular processor (CSV, XLSX, JSON)
│   │   └── video.py              # Video processor (MP4, MOV, AVI, MKV, WEBM)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── aggregate.py          # Group-by aggregations and summaries
│   │   ├── chart.py              # Matplotlib chart generators
│   │   ├── clean.py              # Deduplication, missing-value imputation
│   │   └── transform.py          # Column renaming, date parsing, row filtering
│   └── tests/                    # Automated test suite (315 passing tests)
│
├── frontend/
│   ├── README.md                 # Frontend-specific documentation
│   ├── app.py                    # Streamlit web application
│   ├── client.py                 # Backend API client
│   └── helpers.py                # UI component rendering utilities
│
├── scripts/                      # Utility test generators and scenario verification scripts
├── test_data/                    # Benchmark sample CSV datasets
├── tests/
│   └── fixtures/                 # Canonical test fixtures (documents, images, audio, video, archives)
└── workspace/                    # Local workspace root (runtime sessions excluded via .gitignore)
```

---

## 10. Installation

### 1. Prerequisites
* **Python:** Version `3.11` to `3.14` installed on your system.
* **Git:** Installed and available on your system `PATH`.
* **FFmpeg & FFprobe:** Required for audio and video processing.
  * **Windows:** Install via WinGet:
    ```powershell
    winget install Gyan.FFmpeg
    ```
  * **Linux (Ubuntu/Debian):**
    ```bash
    sudo apt update && sudo apt install -y ffmpeg
    ```
  * **macOS:**
    ```bash
    brew install ffmpeg
    ```

### 2. Clone the Repository
```bash
git clone https://github.com/your-username/datawise.git
cd datawise
```

### 3. Create and Activate Virtual Environment

* **Windows (PowerShell):**
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```

* **Linux / macOS (Bash):**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

---

## 11. Dependencies

Install all pinned project dependencies:

```bash
pip install -r requirements.txt
```

Verify that key packages are properly installed:
```bash
python -c "import fastapi, streamlit, pandas, PIL, mutagen, pydantic; print('All core dependencies imported successfully.')"
```

---

## 12. Environment Variables

DataWise operates out-of-the-box using local execution. A template environment file is provided at `.env.example`.

To customize your configuration:
1. Copy `.env.example` to `.env`:
   * **Windows (PowerShell):**
     ```powershell
     Copy-Item .env.example .env
     ```
   * **Linux / macOS:**
     ```bash
     cp .env.example .env
     ```
2. Configure settings as needed:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DATAWISE_API_URL` | `http://127.0.0.1:8000` | Backend API base URL used by the Streamlit frontend. |
| `FFMPEG_BINARY` | *(Auto-detected)* | Optional explicit filesystem path to `ffmpeg` executable. |
| `FFPROBE_BINARY` | *(Auto-detected)* | Optional explicit filesystem path to `ffprobe` executable. |
| `ANTHROPIC_API_KEY` | *(None / Unused)* | Optional API key reserved for future multimodal vision expansions. |
| `OPENAI_API_KEY` | *(None / Unused)* | Optional API key reserved for future LLM integration. |
| `GEMINI_API_KEY` | *(None / Unused)* | Optional API key reserved for future LLM integration. |

> [!IMPORTANT]
> The `.env` file contains local configuration and potential secrets. It is strictly ignored by `.gitignore` and must never be committed to source control.

---

## 13. Running the Application

Running DataWise requires starting two independent services: the **FastAPI Backend** and the **Streamlit Frontend**. Open two separate terminal windows.

### Terminal 1: Start Backend API
```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Start Uvicorn ASGI server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

> [!IMPORTANT]
> **Single Worker Constraint:** The backend must run with `--workers 1`. The session management and execution state machine rely on an in-process session store. Running multiple worker processes partitions in-memory state across processes and causes intermittent session failures.

* Backend API Docs (Swagger): `http://127.0.0.1:8000/docs`
* Health Check Endpoint: `http://127.0.0.1:8000/health`

### Terminal 2: Start Frontend Web UI
```powershell
# Activate virtual environment
.venv\Scripts\Activate.ps1

# Start Streamlit UI
streamlit run frontend/app.py --server.port 8501
```

* Frontend Web Interface: `http://localhost:8501`

---

## 14. Usage

1. **Access the Interface:** Navigate to `http://localhost:8501` in your browser.
2. **Upload Data:** Drag and drop one or multiple supported files into the upload box (CSV, Excel, JSON, PDF, DOCX, TXT, MD, JPG, PNG, WEBP, WAV, MP3, MP4, MOV, ZIP, TAR, GZ).
3. **Enter Instruction:** Enter your natural-language processing request into the prompt input bar.
4. **Choose Export Format (Tabular):** If processing tabular data, choose your target output format (`CSV`, `Excel`, or `JSON`).
5. **Execute Pipeline:** Click **Run Pipeline**.
6. **Inspect Results:**
   * **Metrics Banner:** View output dimensions, elapsed execution time, and checks passed.
   * **Plain-English Summary:** Read the synthesis explanation of all operations performed.
   * **Data & Media Preview:** Review rendered tables, generated charts, extracted document text, or live audio/video playback.
   * **Plan & Validation Tabs:** Inspect the underlying execution steps and assertion check outcomes.
7. **Download Artifacts:** Click the download button to save the processed file or packaged batch ZIP archive.

---

## 15. Verified Examples

### Example 1: Tabular Transformation & Missing Value Imputation
* **Input File:** `customers.csv`
  ```csv
  id,name,age,purchases
  101,Aarav,25,1200
  102,Diya,,450
  103,Kabir,62,3100
  ```
* **User Instruction:**
  ```text
  clean missing values, drop duplicates, and add a column called Senior set to Yes if age is 60 or above else No
  ```
* **Expected Output:**
  ```csv
  id,name,age,purchases,Senior
  101,Aarav,25.0,1200,No
  102,Diya,43.5,450,No
  103,Kabir,62.0,3100,Yes
  ```

---

### Example 2: Image Resizing & Format Conversion
* **Input File:** `banner.jpg` (Resolution: `1920x1080`)
* **User Instruction:**
  ```text
  resize this image to 800x600 and convert to png
  ```
* **Expected Output:**
  A verified PNG image file formatted to exact `(800, 600)` pixel dimensions, confirmed by magic bytes `\x89PNG\r\n\x1a\n`.

---

### Example 3: Audio Trimming & Bitrate Compression
* **Input File:** `recording.wav` (Duration: `10.0s`, Size: `1.76 MB`)
* **User Instruction:**
  ```text
  trim this audio to first 3 seconds and convert to mp3
  ```
* **Expected Output:**
  An MP3 audio stream of duration `3.0s` (±0.1s tolerance), reduced file size, playable directly inside Streamlit's native audio widget.

---

### Example 4: Video Frame Capture
* **Input File:** `clip.mp4` (Duration: `5.0s`, Resolution: `640x360`)
* **User Instruction:**
  ```text
  extract frame at 2 seconds
  ```
* **Expected Output:**
  A lossless `PNG` screenshot captured at the exact 2.0-second timestamp, rendered in the UI preview tab.

---

### Example 5: Archive Profiling & Safe Recursive Processing
* **Input File:** `dataset_bundle.zip` (Contains: `data1.csv`, `photo.png`)
* **User Instruction:**
  ```text
  extract and process all files in archive
  ```
* **Expected Output:**
  Pre-scan confirms zero path traversal tokens; inner files are routed to their respective domain processors; output members are re-bundled into `result.zip` with complete file manifest reporting.

---

## 16. Testing

The DataWise test suite covers unit tests, tool-level operations, security hardening, API integration, and full Streamlit UI smoke flows.

### Running the Full Test Suite
```powershell
.venv\Scripts\pytest.exe -q --tb=short
```

*Expected Result:* **315 passed**

### Running Specific Test Modules

* **Tabular Tools & Pipeline:**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_tools_clean.py backend/tests/test_pipeline.py
  ```

* **Document Processing:**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_document_processor.py
  ```

* **Image Processing:**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_image_processor.py
  ```

* **Audio & Video Processing:**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_audio_processor.py backend/tests/test_video_processor.py
  ```

* **Archive Security & Zip-Slip Protection:**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_archive_security.py backend/tests/test_archive_processor.py
  ```

* **Frontend Smoke Tests (AppTest):**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_frontend_smoke.py
  ```

---

## 17. Verification Status

Current verification state across all development phases:

| Phase | Description | Status | Automated Test Coverage |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Project Skeleton, Canonical Contracts & Schemas | ✅ Verified | 24 passed tests (`test_schemas.py`, `test_health.py`) |
| **Phase 2** | Input Manager, Session Storage & File Ingestion | ✅ Verified | 16 passed tests (`test_input_manager.py`) |
| **Phase 3** | Data Understanding & Schema Profiling Engine | ✅ Verified | 18 passed tests (`test_understanding.py`) |
| **Phase 4** | Intent Parsing & Step-Mapped Task Planner | ✅ Verified | 22 passed tests (`test_executor.py`, `test_pipeline.py`) |
| **Phase 5** | Execution Engine & Tabular Tool Functions | ✅ Verified | 32 passed tests (`test_tools_clean.py`, `transform.py`) |
| **Phase 6** | Self-Checking Output Validation Layer | ✅ Verified | 19 passed tests (`test_validator.py`) |
| **Phase 7** | Streamlit Frontend Web Interface & REST Client | ✅ Verified | 24 passed tests (`test_frontend_helpers.py`, smoke) |
| **Phase 8** | Adversarial Security Hardening & Error Redaction | ✅ Verified | 12 passed tests (`test_security_adversarial.py`) |
| **Phase 9** | Universal File Detection & Processor Registry | ✅ Verified | 16 passed tests (`test_file_detection.py`) |
| **Phase 10** | Document Processor (PDF, DOCX, TXT, MD) | ✅ Verified | 13 passed tests (`test_document_processor.py`) |
| **Phase 11** | Image Processor (Resize, Crop, Rotate, Convert, Compress)| ✅ Verified | 14 passed tests (`test_image_processor.py`) |
| **Phase 12** | Audio & Video Processors (FFmpeg Branch A) | ✅ Verified | 22 passed tests (`test_audio_processor.py`, `video.py`) |
| **Phase 13** | Archive Security (Zip-Slip), Batch Processing & Packaging| ✅ Verified | 23 passed tests (`test_archive_security.py`, `batch.py`) |
| **Phase 14** | Presentation Processor (`.pptx`) & Final Polish | ⏳ Planned | Scheduled for Phase 14 implementation |

---

## 18. Limitations

To maintain technical accuracy, the following boundaries and constraints of the current implementation are documented:

1. **Heuristic Intent Parsing:** The current planning engine uses a deterministic, rule-based intent parser mapping regex patterns and domain keywords to tools. Complex colloquial instructions that do not match recognized patterns will trigger a clarification request or a parsing error.
2. **Document & Image OCR:** While PDF and document structural extraction works natively via PyMuPDF, image OCR requires a local Tesseract binary installation on your system PATH. Optical character recognition is currently marked disabled in `capabilities.json`.
3. **Audio Transcription:** Speech-to-text transcription is deferred and requires a speech recognition model (e.g., Whisper). Audio capabilities currently focus on stream inspection, trimming, re-encoding, and compression.
4. **Multimodal Vision:** Visual scene description and semantic object classification are deferred and require an external vision API key (`ANTHROPIC_API_KEY` or `GEMINI_API_KEY`).
5. **Backend Concurrency:** The FastAPI backend relies on an in-memory session store and must run with a single worker process (`--workers 1`). Multi-worker deployments require migrating session storage to an external store like Redis.
6. **Archive Formats:** ZIP, TAR, and GZ formats are supported via the Python standard library. The `.7z` format is deferred to avoid unpinned third-party dependencies (`py7zr`).
7. **Resource Boundaries:** Decompression bombs are restricted to 100M pixels for images and 500 MB uncompressed volume for archives. Real hardware limits (available host RAM and disk space) apply to large video and dataset operations.

---

## 19. Security and Privacy

* **Local Execution:** DataWise processes all data locally on your machine. No user data, uploaded files, or dataset rows are transmitted to third-party cloud APIs during default operation.
* **Metadata-Only Separation:** In planned LLM-assisted modes, only structural metadata (column headers, dtypes, dimensions) is shared with reasoning models. Raw data values never leave the local environment.
* **Zip-Slip Defense:** All archive extractions resolve target paths against canonical roots before extraction, immediately aborting if an entry attempts directory traversal (`../`).
* **Path Traversal Protection:** API endpoints strictly validate session IDs against UUID4 regular expressions and sanitize all download filenames. Requests containing `../`, `/`, or `\` are rejected with HTTP 400.
* **Information Leakage Prevention:** Internal server file paths, Python stack traces, and raw JSON exception payloads are intercepted by custom error handlers and replaced with sanitized, human-readable error messages.
* **Strict Session Isolation:** Uploaded user files and generated artifacts are confined to per-session directories in `workspace/sessions/{uuid}/`. Sessions cannot inspect or overwrite adjacent session data.

---

## 20. Development Documentation

For deeper architectural context and engineering specifications, consult the project documentation files:

* [PRD.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD.md) — Core product requirements, user personas, and v1 scope.
* [PRD_V2_ADDENDUM.md](file:///c:/Users/JOSEPH/Desktop/datawise/PRD_V2_ADDENDUM.md) — Scope expansion defining universal format processors (Phases 9–14).
* [flow.md](file:///c:/Users/JOSEPH/Desktop/datawise/flow.md) — End-to-end data and control flow diagrams.
* [techstack.md](file:///c:/Users/JOSEPH/Desktop/datawise/techstack.md) — Technology stack selections and architectural rules.
* [features.md](file:///c:/Users/JOSEPH/Desktop/datawise/features.md) — Detailed feature acceptance criteria.
* [decision.md](file:///c:/Users/JOSEPH/Desktop/datawise/decision.md) — Technical decision log (ADRs) tracking engineering choices.
* [execution.md](file:///c:/Users/JOSEPH/Desktop/datawise/execution.md) — Detailed runtime call chains and module interactions.
* [capabilities.json](file:///c:/Users/JOSEPH/Desktop/datawise/capabilities.json) — Machine-readable processor capability registry.
* [EXAMPLE_COMMANDS.md](file:///c:/Users/JOSEPH/Desktop/datawise/EXAMPLE_COMMANDS.md) — Tested reference prompts for all supported formats.
* [MANUAL_ACTIONS_LOG.md](file:///c:/Users/JOSEPH/Desktop/datawise/MANUAL_ACTIONS_LOG.md) — Log of system prerequisites and external binary setup.

---

## 21. Future Improvements

Planned future enhancements:

* **Phase 14 Presentation Processor:** Native extraction and thumbnail generation for PowerPoint (`.pptx`) decks.
* **Dual-Provider LLM Integration:** Optional integration with Claude / Gemini for flexible natural-language intent parsing and contextual follow-up questions.
* **Speech-to-Text Transcription:** Integration of a lightweight, local Whisper model for automated audio and video transcription.
* **Distributed Session Store:** Redis-backed session and pipeline state manager to allow multi-worker horizontal scaling.
* **Interactive Chart Customization:** Migration from static PNG charts to interactive Plotly or Vega-Lite visualizations in the frontend.

---

## 22. Contributing

Contributions are welcome. Follow these steps to submit changes:

1. **Fork the Repository** on GitHub.
2. **Create a Feature Branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Implement Changes:** Ensure your code adheres to project architectural guidelines and passes all linting standards.
4. **Run the Test Suite:**
   ```bash
   pytest -q
   ```
   All tests must pass before submitting a pull request.
5. **Commit Changes:** Write clear, concise commit messages.
6. **Submit a Pull Request:** Open a PR against the `main` branch with a description of the changes and test results.

---

## 23. License

License information has not yet been specified.

---

## 24. Project Information

* **Project:** DataWise — Autonomous AI Data Processing Agent
* **Repository:** `https://github.com/your-username/datawise`
* **Maintainer:** DataWise Engineering Team
