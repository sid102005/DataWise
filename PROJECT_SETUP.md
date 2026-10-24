# DataWise — Project Setup Guide

Step-by-step instructions to install dependencies and run DataWise locally on Windows, Linux, or macOS.

---

## 1. What you need before starting

| Requirement | Notes |
| :--- | :--- |
| **Python 3.11–3.14** | Reference environment uses Python 3.14.x |
| **Git** | To clone / pull the repo |
| **FFmpeg + FFprobe** | Required for audio and video processing |
| **Disk space** | Session files live under `workspace/sessions/` |
| **Two terminals** | Backend (FastAPI) and frontend (Streamlit) run separately |

Optional later:

- **Tesseract OCR** — needed only if you re-enable OCR in `capabilities.json` (currently disabled)
- **LLM API keys** — reserved for future features; not required for default local runs

There is **no Docker Compose** setup in this repo. Everything runs on the host machine.

---

## 2. Install FFmpeg

Audio/video processors call `ffmpeg` and `ffprobe` as subprocesses. DataWise auto-discovers them from `PATH`, optional env vars, or common Windows WinGet paths.

### Windows (recommended)

```powershell
winget install Gyan.FFmpeg
```

Close and reopen the terminal (or refresh `PATH`), then verify:

```powershell
ffmpeg -version
ffprobe -version
```

### Linux (Ubuntu / Debian)

```bash
sudo apt update && sudo apt install -y ffmpeg
ffmpeg -version
```

### macOS

```bash
brew install ffmpeg
ffmpeg -version
```

If binaries are installed but not on `PATH`, set explicit paths in `.env` (see [§5](#5-environment-variables)).

---

## 3. Clone and create a virtual environment

```bash
cd DataWise
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If script activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should see `(.venv)` in your prompt when the environment is active.

---

## 4. Install Python dependencies

With the venv active:

```bash
pip install -r requirements.txt
```

### Known gap: `mutagen`

The audio processor imports **mutagen** for metadata, but it is **not currently listed** in `requirements.txt`. Install it explicitly:

```bash
pip install mutagen
```

### Verify core imports

```bash
python -c "import fastapi, streamlit, pandas, PIL, mutagen, pydantic; print('All core dependencies imported successfully.')"
```

Also useful (documents / Excel):

```bash
python -c "import fitz, docx, openpyxl; print('Document and Excel libraries OK.')"
```

---

## 5. Environment variables

1. Copy the template:

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

2. Edit `.env` only if you need overrides:

| Variable | Default | Required? | Purpose |
| :--- | :--- | :--- | :--- |
| `DATAWISE_API_URL` | `http://127.0.0.1:8000` | Usually leave as-is | Streamlit → FastAPI base URL |
| `FFMPEG_BINARY` | Auto-detected | Optional | Full path to `ffmpeg` if not on `PATH` |
| `FFPROBE_BINARY` | Auto-detected | Optional | Full path to `ffprobe` if not on `PATH` |
| `ANTHROPIC_API_KEY` | Unused | No | Reserved for future vision / LLM |
| `OPENAI_API_KEY` | Unused | No | Reserved for future LLM |
| `GEMINI_API_KEY` | Unused | No | Reserved for future LLM |

Default operation is **fully local / offline**. Do **not** commit `.env` (it is gitignored).

---

## 6. Important config files (usually no edits needed)

| File | Role |
| :--- | :--- |
| `.streamlit/config.toml` | Raises Streamlit upload limit to **10 GB** (`maxUploadSize = 10000`) |
| `capabilities.json` | Declares which processors/ops are enabled (UI and `/api/capabilities`) |
| `pytest.ini` | Points tests at `backend/tests` with `pythonpath = .` |
| `backend/config.py` | Supported extensions, workspace paths |

Sessions are created automatically under:

```text
workspace/sessions/{session-uuid}/
```

---

## 7. Run the application

You need **two terminals**, both with the venv activated.

### Terminal 1 — FastAPI backend

```powershell
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Equivalent:

```powershell
python -m backend.main
```

**Critical:** always use `--workers 1`. Session state is in-process; multiple workers cause broken / missing sessions.

Check:

- Health: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- Swagger: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Terminal 2 — Streamlit UI

```powershell
.venv\Scripts\Activate.ps1
streamlit run frontend/app.py --server.port 8501
```

Open: [http://localhost:8501](http://localhost:8501)

Optional override (same as `.env`):

```powershell
$env:DATAWISE_API_URL = "http://127.0.0.1:8000"
```

---

## 8. First-run smoke check

1. Open the UI at `http://localhost:8501`.
2. Upload a small CSV from `test_data/` (or `tests/fixtures/`).
3. Prompt example:

   ```text
   clean missing values and drop duplicates
   ```

4. Click **Run Pipeline** and confirm preview + download appear.

More tested prompts: [`EXAMPLE_COMMANDS.md`](EXAMPLE_COMMANDS.md).

---

## 9. Run tests

From the repo root with venv active:

```powershell
.venv\Scripts\pytest.exe -q --tb=short
```

Expected (per project README): **315 passed**.

Useful subsets:

```powershell
# Tabular + pipeline
.venv\Scripts\pytest.exe backend/tests/test_tools_clean.py backend/tests/test_pipeline.py

# Archive security
.venv\Scripts\pytest.exe backend/tests/test_archive_security.py backend/tests/test_archive_processor.py

# Audio / video (needs FFmpeg)
.venv\Scripts\pytest.exe backend/tests/test_audio_processor.py backend/tests/test_video_processor.py

# Frontend smoke
.venv\Scripts\pytest.exe backend/tests/test_frontend_smoke.py
```

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
| :--- | :--- | :--- |
| Frontend cannot reach API | Backend not running / wrong URL | Start uvicorn; confirm `DATAWISE_API_URL` |
| Session / download errors after restart or under load | Multiple uvicorn workers | Restart with `--workers 1` |
| Audio/video fails with binary-not-found | FFmpeg missing or not on `PATH` | Install FFmpeg; or set `FFMPEG_BINARY` / `FFPROBE_BINARY` |
| `ModuleNotFoundError: mutagen` | Missing audio dep | `pip install mutagen` |
| Upload rejected / huge files fail early | Streamlit default limit | Confirm `.streamlit/config.toml` exists |
| OCR-related prompts fail | OCR disabled | Expected; needs Tesseract + capability flag (see `MANUAL_ACTIONS_LOG.md`) |
| Vague prompts ask for clarification | Heuristic intent parser | Use clearer keywords from `EXAMPLE_COMMANDS.md` |

---

## 11. Quick command cheat sheet (Windows)

```powershell
# One-time setup
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install mutagen
Copy-Item .env.example .env
winget install Gyan.FFmpeg

# Every day — Terminal 1
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1

# Every day — Terminal 2
.venv\Scripts\Activate.ps1
streamlit run frontend/app.py --server.port 8501

# Tests
.venv\Scripts\pytest.exe -q --tb=short
```

---

## 12. Related docs

| Doc | Use when you want… |
| :--- | :--- |
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Deep understanding of architecture and flows |
| [`README.md`](README.md) | Full product overview and examples |
| [`EXAMPLE_COMMANDS.md`](EXAMPLE_COMMANDS.md) | Working prompts per format |
| [`capabilities.json`](capabilities.json) | Exact enabled ops / limitations |
| [`MANUAL_ACTIONS_LOG.md`](MANUAL_ACTIONS_LOG.md) | External binary / OCR notes |
