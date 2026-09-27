# features.md — DataWise

Full feature list, organized by phase so you always know what "done for now" looks like.

---

## Phase 1 — MVP ("prove the loop")

**Input**
- [x] Upload CSV
- [x] Upload Excel (.xlsx, multi-sheet aware)
- [x] Upload tabular JSON
- [x] File size/row limit enforcement with clear error message

**Data Understanding**
- [x] Format & encoding detection
- [x] Schema/column detection
- [x] Type inference (numeric / date / categorical / id / text)
- [x] Data profile: row/column count, null %, duplicate %, unique counts

**Instruction Understanding**
- [x] Free-text prompt box
- [x] Parse prompt into one or more objectives
- [x] Ask a clarifying question when genuinely ambiguous (not for everything)

**Cleaning**
- [x] Remove duplicate rows (whole-row or by key column)
- [x] Handle missing values (mean/median/mode/drop/fill-value — chosen sensibly by type)
- [x] Fix obvious type mismatches (e.g. numbers stored as text)
- [x] Standardize inconsistent date formats

**Transformation**
- [x] Rename/reorder columns
- [x] Filter rows by condition ("only region = X")
- [x] Basic derived columns (e.g. total = price × quantity)

**Aggregation**
- [x] Group by + sum/avg/count/min/max
- [x] Sort ascending/descending
- [x] Top-N / bottom-N

**Visualization**
- [x] Bar chart
- [x] Line chart
- [x] Pie chart

**Validation**
- [x] Row-count sanity check
- [x] Post-clean null check
- [x] "Requested output exists" check
- [x] Bounded auto-retry on failure (max 2)

**Output**
- [x] Download cleaned/processed file
- [x] Result table preview in UI
- [x] Chart render in UI
- [x] Plain-English "what I did" summary
- [x] Plain-English error messages (no stack traces to the user)

**Trust / Transparency**
- [x] Show the execution plan (before or after run)
- [x] Show what changed (rows removed, nulls filled, columns added)

---

## Phase 2 — Broaden Format & Intelligence

**Input**
- [ ] PDF text + table extraction
- [ ] DOCX extraction
- [ ] Plain text / log files
- [ ] Basic image OCR (table-in-image → structured data)
- [ ] Multi-file upload for comparison tasks

**Analysis**
- [ ] Correlation analysis
- [ ] Distribution summaries (mean/median/std/outlier flags)
- [ ] Comparison between two datasets/time periods ("2024 vs 2025")

**ML (explainable models only)**
- [ ] Regression (predict a numeric target)
- [ ] Classification (predict a category)
- [ ] Model performance summary in plain English (not just raw metrics)

**Conversational refinement**
- [ ] Follow-up instructions on an existing result ("now exclude region X")
- [ ] Plan amendment instead of full re-plan

**Reporting**
- [ ] Auto-generated summary report (PDF or DOCX) combining tables, charts, and narrative

**Extraction**
- [ ] "Extract all tables from this PDF into Excel"

---

## Phase 3 — Scale & Integrate

- [ ] Live database connections (read-only)
- [ ] API-source ingestion
- [ ] Scheduled/recurring jobs ("run this every Monday, email me the result")
- [ ] Time-series specific handling (trend, seasonality)
- [ ] Multi-user accounts & saved pipeline history
- [ ] "Re-run this pipeline on new data" (save a plan as a reusable template)
- [ ] Public developer API with auth & rate limiting
- [ ] Audio/video metadata-level data support (exploratory)

---

## Explicitly Out of Scope (for the foreseeable roadmap)

- Training custom/deep-learning models from scratch
- Real-time streaming data pipelines
- Acting as a general-purpose chatbot unrelated to the uploaded data
- Claiming to support "any" file type without an explicit, enforced allow-list
- Letting the LLM directly compute or state numeric results without them coming from real executed code

---

## How to Use This With Antigravity

Treat each checkbox group above as a candidate **mission**. Good mission sizing:
- Too big: "Build DataWise" (no agent can plan this well)
- Too small: "Add a button" (wastes the planning overhead)
- Right size: "Implement Stage 1 (Data Understanding) for CSV and Excel: format detection, schema detection, and a DataProfile object, with unit tests" — this is scoped, testable, and reviewable as one Artifact/plan.

Suggested first five missions, pulled from Phase 1:
1. Data Understanding module (CSV + Excel) + DataProfile schema + tests
2. Tool layer: cleaning functions (dedupe, missing values, type fixes) + tests
3. Planner: turn a sample set of objectives into step lists (start with hardcoded objective→step mapping, add LLM parsing after)
4. Executor + Validator loop wired together end-to-end on the cleaning path
5. Minimal UI (Streamlit): upload, prompt box, show plan, show result, download
