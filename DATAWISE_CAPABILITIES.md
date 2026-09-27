# DataWise Capabilities

This document tracks the verified, supported capabilities of the DataWise Universal Format Processor architecture.

## Currently Supported

### 1. Tabular Processor (CSV, Excel, JSON)
- **Transform**: Clean missing values, drop columns, add columns, rename columns, filter rows, sort values, deduplicate.
- **Analyze**: Group-by aggregations, statistical summaries, numeric distributions.
- **Visualize**: Bar charts, line charts, pie charts.

### 2. Document Processor (PDF, DOCX, TXT, MD) — Phase 10
- **Extraction**: Extract text and tables from PDF, DOCX, TXT, MD.
- **Analysis**: Word counts, heading detection, document metadata profiling.
- **Transform**: Normalization and export across document formats.
- **Limitations**:
  - OCR is disabled pending Tesseract binary installation (`MANUAL_ACTIONS_LOG.md`).
  - Summarization is deferred to future phase for validation design reasons.
  - Legacy `.doc` and `.docm` are detected and rejected.

### 3. Image Processor (JPEG, PNG, GIF, BMP, WEBP, TIFF) — Phase 11
- **Structural Transformations**: Resize (exact dimensions), Crop (sub-region bounds), Rotate (90/180/270 degrees with dimension swap and pixel tracking).
- **Format Conversion**: Convert between JPEG, PNG, WEBP, GIF, BMP, TIFF.
- **Optimization**: Lossy compression with quality control and verified size reduction.
- **Analysis**: Metadata profiling (width, height, format, color mode, EXIF).
- **Security**: Decompression bomb guard active (`Image.MAX_IMAGE_PIXELS`).
- **Limitations**:
  - OCR is disabled pending Tesseract binary installation (`MANUAL_ACTIONS_LOG.md`).
  - Multimodal description and classification are deferred (require vision LLM API key).
  - Background removal is not supported.

### 4. Audio Processor (MP3, WAV) — Phase 12 (Branch A: FFmpeg)
- **Metadata Extraction**: Sample rate, duration, channels, audio codec profiling.
- **Manipulation**: Deterministic trimming, format conversion (WAV <-> MP3), lossy compression via bitrates.
- **Playback**: Streamlit native audio player rendering.
- **Limitations**:
  - Transcription deferred (requires speech-to-text model).

### 5. Video Processor (MP4, MOV, AVI, MKV, WEBM) — Phase 12 (Branch A: FFmpeg)
- **Metadata Extraction**: Resolution (width x height), duration, video/audio codecs, framerate profiling.
- **Manipulation**: Deterministic trimming, frame extraction at timestamps to PNG, video resizing, format conversion, audio track extraction to MP3/WAV.
- **Playback**: Streamlit native video player and extracted frame preview rendering.
- **Limitations**:
  - AI video tracking and complex transitions/effects deferred to future phases.

### 6. Archive Processor (ZIP, TAR, GZ) — Phase 13
- **Security Guard**:
  - **Zip-Slip Protection**: Canonical path traversal defense rejecting any target containing `..`, absolute paths, or outside the sandboxed extraction root.
  - **Archive Bomb Protection**: Central directory / header uncompressed size check capping total extraction at 500 MB without uncompressing to disk.
  - **Entry Count Cap**: Maximum 10,000 entries per archive.
  - **Session Isolation**: Safe workspace isolation in `backend/data/sessions/<session_id>/archive_workspace/` with guaranteed cleanup in `finally` blocks.
- **Inspection & Profiling**: Entry listing, uncompressed file size reporting, inner file category detection via magic bytes.
- **Recursive Processing**: Automatically routes extracted inner members to their respective domain processors (tabular, image, doc, audio, video) and re-packages processed members into a safe output archive.

### 7. Multi-File & Batch Processing — Phase 13
- **Multi-File Ingestion**: Frontend uploader accepts multiple files (`accept_multiple_files=True`) and backend `POST /api/pipeline/run` accepts `files: list[UploadFile]`.
- **Cross-Category Routing**: Each file in the batch is independently sniffed by magic bytes and routed to its appropriate domain processor.
- **Partial Success Semantics**: Heterogeneous batch runs report partial success honestly: files matching the prompt operation succeed, while unsupported or erroring files are cleanly recorded without aborting the entire batch.
- **Safe Packaging**: All processed batch outputs are consolidated into a session-isolated, zip-slip protected ZIP archive for single-click download.

---

## Planned (Not Yet Implemented / Deferred)

- **Presentation Processor (Phase 14)**: PPTX slide text, tables, shapes, and thumbnail generation.
- **7Z Archive Format (Explicitly Deferred)**: Requires `py7zr` external dependency; standard library `zipfile` and `tarfile` cover all primary enterprise use cases without bloat.
