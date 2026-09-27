# Manual Actions Log

This file tracks capabilities that require missing system dependencies, API keys, or external accounts.

## Protocol for Missing Dependencies
If a capability requires something only the user can provide:
1. STOP implementing that specific capability.
2. Append an entry to this file in the exact format shown below.
3. Continue implementing other capabilities that do not depend on the missing piece.
4. In the Final Report for the phase, surface the contents of this file prominently under a "MANUAL ACTION NEEDED" heading.

### Format
```markdown
## [Capability name]
**Blocked on:** (e.g., "FFMPEG_PATH not found on system" / "requires ANTHROPIC_API_KEY for vision-based image description")
**Why it's needed:** (plain explanation — what this specific capability cannot do without it)
**Exact action required from the user:** (e.g., "Install FFmpeg and ensure it's on PATH" / "Add ANTHROPIC_API_KEY=... to .env")
**What still works without it:** (be honest — most capabilities in a phase should NOT be blocked by one missing dependency; only the specific feature that needs it)
```

---

*(No entries for Phase 9)*

### Action Required: Install Tesseract System Binary
- **Date:** 2026-09-26
- **Context:** Phase 10 Document Processor (extract_text_ocr)
- **Problem:** OCR capability requires the Tesseract system binary, which is not installed in the environment. Python package pytesseract requires this external system library.
- **Action:**
  1. Install Tesseract OCR for Windows (e.g., via scoop, winget, or official installer).
  2. Ensure 	esseract is in the system PATH.
  3. Install the pytesseract python wheel (pip install pytesseract).
  4. Re-enable OCR in capabilities.json.
- **Status:** PENDING

---

## Audio & Video Manipulation (Phase 12)
- **Status:** **RESOLVED** (2026-09-27)
- **Resolution:** FFmpeg 9.0.2 installed via `winget install Gyan.FFmpeg`. While Windows PATH environment changes require a shell restart for inheritance, `backend/core/ffmpeg_locator.py` implements a path-independent 3-tier discovery strategy (PATH -> Environment variable override -> WinGet package directory probe). FFmpeg and FFprobe binaries are actively discovered at:
  `C:\Users\JOSEPH\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe`
- **Active Capabilities:** Full Branch A unlocked for Audio (extract_metadata, trim, convert_format, compress) and Video (extract_metadata, trim, extract_frame, resize, convert_format, compress, extract_audio). No manual action required.

---

## Archive & Batch Processing (Phase 13)
- **Status:** **COMPLETE** (2026-09-27)
- **Dependencies:** Standard Library only (`zipfile`, `tarfile`, `gzip`). Zero external binaries or third-party dependencies required. 7Z format is explicitly deferred. No manual action required.
