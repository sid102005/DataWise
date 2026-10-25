# DataWise — Usage Guide

How to run DataWise and use every major feature (tabular ML cleaning, documents, images, audio, video, archives). Written so anyone can follow the steps and re-run the same tests.

A shareable PDF copy of this guide is available as **`USAGE_GUIDE.pdf`** in the repo root (regenerate with `python scripts/export_usage_guide_pdf.py`).

---

## 1. Start the app

From the repo root (`DataWise/`):

```powershell
# One-time (if not done): create venv + install
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Every day — easiest
.\start.ps1
```

Or two terminals:

```powershell
# Terminal 1 — API
.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 1

# Terminal 2 — UI
.venv\Scripts\Activate.ps1
streamlit run frontend/app.py --server.port 8501
```

Open:

| Service | URL |
| :--- | :--- |
| UI | http://localhost:8501 |
| API health | http://127.0.0.1:8000/health |
| API docs | http://127.0.0.1:8000/docs |

**Important:** always use `--workers 1` for the API.

---

## 2. General workflow (all file types)

1. Open the UI.
2. Upload one (or more) files.
3. Type a plain-English prompt.
4. Click **Run Pipeline**.
5. Review preview / summary / plan steps.
6. Download the result.

Same idea via API:

```powershell
curl -X POST "http://127.0.0.1:8000/api/pipeline/run" `
  -F "prompt=clean this for ML" `
  -F "file=@test_files/tabular/messy_customers.csv"
```

---

## 3. Tabular files (CSV / JSON / Excel) — ML cleaning

### Test files

| File | Path | Use for |
| :--- | :--- | :--- |
| Messy CSV / JSON / Excel | `test_files/tabular/messy_customers.*` | ML clean |
| Sales by region | `test_files/tabular/sales_by_region.csv` (also `.json` / `.xlsx`) | Bar/pie charts + convert |
| Monthly revenue | `test_files/tabular/monthly_revenue.csv` | Line charts |
| Product mix | `test_files/tabular/product_mix.csv` | Pie / bar charts |
| Store sales (multi-row) | `test_files/tabular/store_sales.csv` | Bar chart with auto groupby |

Also see `test_files/tabular/CHARTS_README.md`, plus older samples under `test_data/` and `tests/fixtures/sample.csv`.

### What `clean_for_ml` does

When you ask to clean tabular data, DataWise:

1. Strips whitespace  
2. Turns `N/A` / `null` / blanks / `-` / `?` into missing values  
3. Drops empty columns  
4. Removes duplicate rows  
5. Coerces numeric text → numbers  
6. Imputes remaining nulls (median / mode)  
7. Standardizes dates to `YYYY-MM-DD`  
8. Drops constant (no-signal) columns  

### Prompts to try

| Prompt | Expected |
| :--- | :--- |
| `clean this for ML` | Full ML prep pipeline |
| `clean this CSV so I can use it in my ML project` | Same |
| `prepare this data for machine learning` | Same |
| `sort by Age ascending` | Sort only (all rows) |
| `show only Name and Age columns` | Column projection |
| `only display 2 columns` | Keep first 2 columns |
| `filter rows where Age > 30` | Row filter |
| `group by Region and sum Purchase` | Groupby aggregate |
| `top 5 by Purchase` | Sort + top N |
| `remove the Phone column` | Drop column (if present) |

### Convert formats (CSV ↔ JSON ↔ Excel)

The UI export dropdown is a default only — **convert wording in the prompt overrides it**.

| Prompt | Expected |
| :--- | :--- |
| `convert this csv to json` | Download `.json` |
| `convert this json to csv` | Download `.csv` |
| `convert to xlsx` / `convert to excel` | Download `.xlsx` |
| `save as json` | Download `.json` |

Upload `sales_by_region.csv` (or `.json` / `.xlsx`) and use any prompt above.

### Charts (simple commands)

Use the clean chart fixtures (not `messy_customers` until after clean). Column names in the prompt should match the file headers.

| File | Prompt |
| :--- | :--- |
| `sales_by_region.csv` | `bar chart of Sales by Region` |
| `sales_by_region.csv` | `pie chart of Sales by Region` |
| `monthly_revenue.csv` | `line chart of Revenue by Month` |
| `product_mix.csv` | `pie chart of Units by Product` |
| `store_sales.csv` | `bar chart of Sales by Region` (sums stores first) |

Charts appear in the result artifacts / preview as PNG. Leave export as CSV unless you also want a converted download.

### How to test (manual)

1. Upload `test_files/tabular/messy_customers.csv`.
2. Prompt: `clean this for ML`.
3. Confirm rows drop (dupes gone), empty/constant columns removed, download works.
4. Repeat with `.json` and `.xlsx`.
5. Upload `sales_by_region.csv` → `convert this csv to json` → download JSON.
6. Upload `sales_by_region.csv` → `bar chart of Sales by Region` → confirm chart PNG.

### How to test (API smoke)

```powershell
.venv\Scripts\Activate.ps1
python -c "import httpx; from pathlib import Path; p=Path('test_files/tabular/messy_customers.csv'); r=httpx.post('http://127.0.0.1:8000/api/pipeline/run', data={'prompt':'clean this for ML'}, files={'file':(p.name,p.read_bytes(),'text/csv')}, timeout=120); print(r.json()['status'], r.json()['total_rows'], r.json()['preview_columns'])"
python -c "import httpx; from pathlib import Path; p=Path('test_files/tabular/sales_by_region.csv'); r=httpx.post('http://127.0.0.1:8000/api/pipeline/run', data={'prompt':'convert this csv to json','export_format':'csv'}, files={'file':(p.name,p.read_bytes(),'text/csv')}, timeout=120); j=r.json(); print(j['status'], j.get('result_filename'), j.get('summary'))"
python -c "import httpx; from pathlib import Path; p=Path('test_files/tabular/sales_by_region.csv'); r=httpx.post('http://127.0.0.1:8000/api/pipeline/run', data={'prompt':'bar chart of Sales by Region'}, files={'file':(p.name,p.read_bytes(),'text/csv')}, timeout=120); j=r.json(); print(j['status'], [a.get('filename') for a in j.get('artifacts') or []])"
```

---

## 4. Documents (PDF / DOCX / TXT / MD)

### Test files

Generate (or refresh) fixtures:

```powershell
.venv\Scripts\python.exe scripts\generate_document_test_files.py
```

| File | Path | Best for |
| :--- | :--- | :--- |
| PDF report | `test_files/documents/sample_report.pdf` | text, entities, pages, links, metadata |
| DOCX invoice | `test_files/documents/sample_invoice.docx` | tables→CSV, headings, key-values |
| TXT report | `test_files/documents/sample_report.txt` | entities, redact, summary |
| Markdown | `test_files/documents/sample_overview.md` | headings, links |

### Features and prompts

| Feature | Example prompt | Notes |
| :--- | :--- | :--- |
| Extract text | `extract text from this document` | Default baseline |
| Clean text | `clean this document text` | Whitespace + header/footer noise |
| Word count | `count the words in this document` | |
| Metadata | `extract document metadata` | pages, author, size, etc. |
| Headings / outline | `extract headings` / `show the outline` | PDF/DOCX/MD |
| Tables → CSV | `extract all tables` | Writes `table_1.csv`, … in session folder |
| Split by page | `split this PDF by page` | Writes `page_1.txt`, … |
| Entities | `extract emails, phones, dates, and amounts` | Deterministic regex |
| Key-value / invoice fields | `extract invoice fields` / `extract key values` | `Label: value` lines |
| Find mentions | `find all mentions of "Revenue"` | Quotes recommended |
| Links | `extract all links and urls` | URLs + emails |
| Language | `detect the language of this document` | Lightweight heuristic |
| Images / figures | `extract images from this PDF` | PDF only |
| Redact PII | `redact emails and phone numbers` | Masks PII in text |
| Summary | `summarize this document` | Extractive (no LLM required) |
| Q&A | `what is the invoice number?` | Uses LLM if API key set; else returns extracted text fallback |
| OCR (scanned PDF / image) | `OCR this scanned PDF` / `extract text with OCR` | Needs Tesseract — see **§5 OCR setup** |
| Convert / export | `convert this document to markdown` | Download as txt/md/json/docx/pdf |

### How to test each document feature (checklist)

1. Start backend + UI.  
2. Upload `test_files/documents/sample_invoice.docx`.  
3. Run: `extract all tables` → download / check session for CSV artifacts.  
4. Upload `sample_report.pdf`.  
5. Run in turn:
   - `extract text from this document`
   - `extract emails, phones, dates, and amounts`
   - `extract invoice fields`
   - `find all mentions of "Revenue"`
   - `split this PDF by page`
   - `extract document metadata`
   - `summarize this document`
6. Upload `sample_report.txt` → `redact emails and phone numbers`.  
7. Upload `sample_overview.md` → `extract headings`.  
8. After OCR is installed (§5): upload a scanned PDF / image → `OCR this scanned PDF` or `extract text with OCR`.

---

## 5. OCR setup (Tesseract) — share these steps with friends

OCR lets DataWise read **scanned PDFs** (image-only pages) and **extract text from images**.  
Normal text-layer PDFs / DOCX / TXT work **without** OCR. Install this only if you need scanned-doc or image text extraction.

### What gets installed

| Piece | Role |
| :--- | :--- |
| **Tesseract OCR** (system app) | The actual engine that reads text from images |
| **pytesseract** (Python package) | Bridge between DataWise and Tesseract |

DataWise looks for Tesseract in this order: `TESSERACT_BINARY` in `.env` → PATH → common Windows paths like `C:\Program Files\Tesseract-OCR\tesseract.exe`.

---

### Step A — Install the Tesseract system binary

#### Windows (recommended)

Open **PowerShell** and run:

```powershell
winget install --id UB-Mannheim.TesseractOCR -e --source winget --accept-package-agreements --accept-source-agreements
```

Then **close and reopen** the terminal (so PATH refreshes), and verify:

```powershell
tesseract --version
```

You should see a version line (e.g. `tesseract 5.x.x`).

If `tesseract` is not found but it installed under Program Files, either:

1. Add `C:\Program Files\Tesseract-OCR` to your user PATH, **or**
2. Put this in your project `.env` (copy from `.env.example` if needed):

```env
TESSERACT_BINARY=C:\Program Files\Tesseract-OCR\tesseract.exe
```

#### Linux (Ubuntu / Debian)

```bash
sudo apt update
sudo apt install -y tesseract-ocr
tesseract --version
```

#### macOS

```bash
brew install tesseract
tesseract --version
```

---

### Step B — Install the Python package (inside the DataWise venv)

From the repo root (`DataWise/`):

**Windows**

```powershell
.venv\Scripts\Activate.ps1
pip install pytesseract
# Or install everything again:
pip install -r requirements.txt
```

**Linux / macOS**

```bash
source .venv/bin/activate
pip install pytesseract
# Or:
pip install -r requirements.txt
```

`pytesseract` is already listed in `requirements.txt`, so a normal `pip install -r requirements.txt` is enough if the venv is fresh.

---

### Step C — Verify DataWise can see Tesseract

With the venv active, from the repo root:

```powershell
python -c "from backend.core.ocr_locator import get_tesseract_path, is_tesseract_available; print('available:', is_tesseract_available()); print('path:', get_tesseract_path())"
```

Expected:

```text
available: True
path: C:\Program Files\Tesseract-OCR\tesseract.exe
```

(Path may differ on Linux/macOS.)

If `available: False`, set `TESSERACT_BINARY` in `.env` to the full path of `tesseract` / `tesseract.exe`, save, and run the check again.

---

### Step D — Restart DataWise

Stop the backend and UI, then start again (so they pick up env / PATH):

```powershell
.\start.ps1
```

Or use **Run and Debug → DataWise: Full Stack** (F5).

---

### Step E — Test OCR in the UI

1. Open http://localhost:8501  
2. Try one of these:

| File to upload | Prompt |
| :--- | :--- |
| Scanned / image-only PDF | `OCR this scanned PDF` |
| Scanned PDF | `extract text` (auto-OCR if there is no text layer) |
| JPG / PNG image | `extract text with OCR` |

3. Confirm the result text appears (and download works).

Fixture tip: `tests/fixtures/documents/sample_scanned.pdf` is an image-only PDF made for OCR testing.

---

### OCR prompts (cheat sheet)

| Prompt | Works on |
| :--- | :--- |
| `OCR this scanned PDF` | PDF |
| `extract text with OCR` | PDF or image |
| `extract text` | PDF — uses OCR automatically if no text layer |

---

### OCR troubleshooting

| Problem | Fix |
| :--- | :--- |
| `tesseract: command not found` | Reopen terminal after install; or set `TESSERACT_BINARY` in `.env` |
| `available: False` in Step C | Point `.env` at the real `tesseract.exe` path; restart backend |
| `ModuleNotFoundError: pytesseract` | Activate `.venv` and run `pip install pytesseract` |
| OCR returns empty / garbage text | Scan quality is low; try a clearer image (Tesseract limitation) |
| Text PDFs work, scanned ones fail | OCR binary missing — finish Steps A–D |
| Friend on another PC | They must run Steps A–E on **their** machine (Tesseract is not bundled in the repo) |

---

## 6. Images

Supported ops (see also `EXAMPLE_COMMANDS.md`):

| Prompt example | Result |
| :--- | :--- |
| `resize this image to 1024x1024` | Resize |
| `crop image to 50, 50, 450, 350` | Crop |
| `rotate this image by 90 degrees` | Rotate |
| `convert image to PNG` | Format convert |
| `compress this image with quality 50` | Compress |
| `extract image metadata and dimensions` | Metadata |
| `extract text with OCR` | Read text from the image (needs §5) |

Fixtures: `tests/fixtures/images/` (generate via `scripts/generate_image_fixtures.py` if needed).

---

## 7. Audio

| Prompt example | Result |
| :--- | :--- |
| `extract audio metadata` | Duration, sample rate, channels |
| `trim this audio to first 2 seconds` | Trim |
| `convert audio to mp3` | Convert |
| `compress this audio` | Compress |

Requires **FFmpeg** on PATH (`ffmpeg -version`).

---

## 8. Video

| Prompt example | Result |
| :--- | :--- |
| `extract video metadata` | Metadata |
| `trim this video to first 3 seconds` | Trim |
| `extract frame at 1 second` | Frame image |
| `extract audio from this video` | Audio track |
| `resize this video` | Resize (when planned) |

Requires **FFmpeg**.

---

## 9. Archives (ZIP / TAR / GZ)

| Prompt example | Result |
| :--- | :--- |
| `list files in this archive` | Member listing |
| `extract and process all files in archive` | Safe extract + process |

Security: path traversal / zip-bomb guards are built in.

---

## 10. Automated tests (developers)

```powershell
.venv\Scripts\Activate.ps1

# Full suite
.venv\Scripts\pytest.exe -q --tb=short

# Useful subsets
.venv\Scripts\pytest.exe backend/tests/test_tools_clean.py -q
.venv\Scripts\pytest.exe backend/tests/test_document_processor.py -q
.venv\Scripts\pytest.exe backend/tests/test_pipeline.py -q
.venv\Scripts\pytest.exe backend/tests/test_regression_emergency_fix.py -q
```

OCR-specific smoke (needs Tesseract — see §5):

```powershell
.venv\Scripts\pytest.exe backend/tests/test_document_processor.py::test_ocr_scanned_pdf backend/tests/test_image_processor.py::test_extract_text_ocr_gating -q --tb=short
```

---

## 11. Feature map (quick reference)

| Area | Main capability | Test folder |
| :--- | :--- | :--- |
| Tabular ML clean | `clean_for_ml` | `test_files/tabular/` |
| Documents | extract / tables / entities / redact / summary / … | `test_files/documents/` |
| OCR | scanned PDF + image text | §5 + `tests/fixtures/documents/sample_scanned.pdf` |
| Images | resize, crop, rotate, convert, compress, OCR | `tests/fixtures/images/` |
| Audio / video | metadata, trim, convert (FFmpeg) | `tests/fixtures/audio/`, `tests/fixtures/video/` |
| Archives | list / safe extract | `tests/fixtures/archives/` |

---

## 12. Related docs

| Doc | Purpose |
| :--- | :--- |
| [`PROJECT_SETUP.md`](PROJECT_SETUP.md) | Install from scratch |
| [`PROJECT_OVERVIEW.md`](PROJECT_OVERVIEW.md) | Architecture |
| [`EXAMPLE_COMMANDS.md`](EXAMPLE_COMMANDS.md) | More prompt examples |
| [`capabilities.json`](capabilities.json) | Enabled processors / limits |
| [`test_files/README.md`](test_files/README.md) | Index of tabular + document fixtures |
| [`test_files/documents/README.md`](test_files/documents/README.md) | Document fixtures |
| [`MANUAL_ACTIONS_LOG.md`](MANUAL_ACTIONS_LOG.md) | External binaries (Tesseract, etc.) |

---

## 13. Troubleshooting

| Problem | Fix |
| :--- | :--- |
| UI cannot reach API | Start uvicorn on port 8000; check `DATAWISE_API_URL` in `.env` |
| Weird session errors | Restart API with `--workers 1` |
| Audio/video fails | Install FFmpeg; reopen terminal |
| Document / image OCR fails | Follow **§5 OCR setup** (Tesseract + `pytesseract`, optional `TESSERACT_BINARY`, restart app) |
| Clean prompt does nothing unexpected | Use clearer prompts from this guide |
| Huge upload rejected | Confirm `.streamlit/config.toml` has `maxUploadSize = 10000` |


