# PRD.md — DataWise
**Autonomous AI Data Processing Agent**

> **NOTE:** See `PRD_V2_ADDENDUM.md` for the v2 universal-format scope expansion.


Version 0.1 · Draft for build with Google Antigravity

---

## 1. Vision

Most people who need something done to their data — clean it, reshape it, analyze it, chart it — don't know which tool, library, or technique to use. DataWise removes that barrier: the user gives **data + a plain-English instruction**, and the agent figures out the rest — what the data is, what needs to happen to it, how to do it, whether it worked, and how to hand back a result that makes sense.

> "Give DataWise your data and tell it what you want. DataWise figures out how to do it."

DataWise is **not** a chatbot that talks about data. It is an agent that acts on data, following a fixed loop:

```
Understand → Plan → Execute → Validate → Deliver
```

---

## 2. Problem Statement

Traditional data work requires the user to already know:
- What format their data is in and what tool opens it
- Which library/technique cleans or transforms it
- How to write the analysis (SQL, pandas, formulas)
- How to validate that the result is actually correct
- How to turn the result into something shareable

This is a real barrier for non-technical users, and even for technical users it's repetitive, error-prone busywork for routine tasks.

---

## 3. Goals

- **G1** — A user can upload one file and type one instruction, in natural language, and get a correct, usable result.
- **G2** — The agent explains *what it did*, not just the output (trust + transparency).
- **G3** — The agent self-checks its own output before returning it (validation loop), and retries/corrects on failure instead of silently returning a bad result.
- **G4** — The system is explicit about what it does and doesn't support — never silently guesses wrong and hands back garbage.
- **G5** — Architecture is modular: new data types and new operations can be added without rewriting the core loop.

## 3.1 Non-Goals (for v1)

- Not a general-purpose chatbot / not a BI dashboard replacement
- Not promising to handle "any data of any kind" — v1 explicitly scopes to a defined format list (see §6)
- Not a real-time streaming data system in v1
- Not multi-user collaboration / team workspaces in v1
- Not training or hosting custom ML models in v1 (uses pre-built, well-understood ML routines only — e.g. regression, classification via scikit-learn — not deep learning)

---

## 4. Target Users

| Persona | Need | Example |
|---|---|---|
| Non-technical business user | Clean/analyze data without learning Excel formulas or Python | "Clean this and show top customers" |
| Student / researcher | Quick stats, cleaning, charts on a dataset | "Find correlation between X and Y" |
| Analyst / junior data person | Automate repetitive prep work | "Standardize dates and remove dupes in all these files" |
| Developer (secondary) | Use DataWise as an API/tool inside their own app | Programmatic cleaning/transform endpoint |

---

## 5. Core User Story (MVP)

> As a user, I upload a CSV or Excel file and type an instruction like "clean this data and show me the top 10 customers by revenue." DataWise detects the format, profiles the data, plans the steps needed, executes them, checks the result is sane, and gives me back a cleaned file + a result table + a plain-English summary of what changed.

---

## 6. Scope

### MVP (Phase 1) — "Prove the loop works"
- **Input formats:** CSV, Excel (.xlsx), JSON (tabular)
- **Operations:** cleaning (missing values, duplicates, type fixes), basic transformation (renaming, date formatting, filtering), aggregation (group by, sum/avg/count/top-N), basic charting (bar/line/pie)
- **Output:** cleaned file download, result table, one chart, plain-English change summary
- **Validation:** row-count sanity check, null-check, type-check, "did the requested column/metric actually get produced" check
- **Interface:** simple web UI (upload + prompt box + results panel)

### Phase 2 — "Broaden format & intelligence"
- Input formats: PDF (tables/text extraction), DOCX, TXT/log files, basic image OCR
- Operations: statistical analysis (correlation, distributions, hypothesis-style summaries), simple ML (regression/classification via scikit-learn), multi-file comparison ("compare 2024 vs 2025")
- Multi-step conversations (user can refine: "now exclude region X")
- Report generation (auto-written PDF/Word summary)

### Phase 3 — "Scale & integrate"
- Database/API/live-source connections
- Scheduled/recurring jobs ("run this every Monday")
- Audio/video/time-series data
- Multi-user workspaces, history, saved pipelines
- Public API for developers

**Explicit rule:** never market the product as "handles any data" — always state the currently supported format list in the UI.

---

## 7. Functional Requirements

### FR1 — Data Understanding
- Detect file format and encoding
- Parse structure (columns, types, headers, sheet names for Excel)
- Profile data: row/column counts, null %, duplicate %, unique value counts, basic type inference (numeric/date/categorical/text/id)
- Flag data quality issues to the user before acting on them if ambiguous (e.g. "column 'Date' has 3 formats mixed — should I standardize to DD-MM-YYYY?")

### FR2 — Intent Understanding
- Parse the user's natural-language prompt into one or more discrete objectives (e.g., "clean" + "rank by revenue" = 2 objectives)
- Map each objective to a known operation category (cleaning / transform / aggregation / stats / ML / visualization / extraction / comparison / report)
- If the prompt is ambiguous or objective is unsupported, ask a clarifying question rather than guessing silently

### FR3 — Task Planning
- Convert objectives into an ordered, explicit step list (a "plan") before execution
- Plan must be inspectable/loggable (this becomes the audit trail / Antigravity Artifact-style plan)
- Steps map 1:1 to tool-layer functions (see techstack.md) — the LLM does not freehand-manipulate data

### FR4 — Execution
- Execute plan steps in order using the tool layer (pandas/numpy/etc., never the LLM doing arithmetic itself)
- Each step's output is captured for validation and for the "what changed" summary
- Execution must be sandboxed (no arbitrary shell/network access from generated code)

### FR5 — Validation
- After execution, automatically check:
  - Row count didn't unexpectedly drop to 0 or change implausibly
  - Nulls handled if cleaning was requested
  - Requested output (column/metric/chart) actually exists
  - Data types are correct post-transform
- On failure: revise plan and retry (bounded retry count, e.g. max 2 retries) before surfacing an error to the user

### FR6 — Output Generation
- Return: processed file (in same or requested format), result table/preview, chart(s) if relevant, and a plain-English "what I did" summary (mapped from the executed plan)
- User can download results or (Phase 2+) continue refining conversationally

### FR7 — Transparency & Control
- User can see the plan before or after execution (configurable)
- User can see exactly which rows/columns were changed, added, or removed
- Errors are shown in plain language, not stack traces

---

## 8. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Performance** | MVP target: files up to ~50MB / ~500k rows processed in under 60s for standard clean+aggregate operations |
| **Reliability** | Validation + bounded auto-retry before failing to the user; failures must be explainable, never silent |
| **Security** | Sandboxed code execution; no arbitrary file-system or network access from generated/execution code; uploaded data isolated per session/user |
| **Privacy** | User data not used to train models; data purged after a defined retention window (configurable) |
| **Extensibility** | Adding a new data format or operation should not require touching the core Understand→Plan→Execute→Validate loop |
| **Explainability** | Every output must be traceable back to the plan step(s) that produced it |
| **Cost control** | Cap LLM calls per request (planning + validation reasoning only — not raw data passed through the LLM at scale) |

---

## 9. Success Metrics (MVP)

- **Task success rate:** % of user requests that complete without manual correction
- **Validation catch rate:** % of bad outputs caught by the validation step before reaching the user
- **Time-to-result:** median time from upload+prompt to delivered output
- **Clarification rate:** % of requests needing a clarifying question (lower isn't always better — track it, don't just minimize it)
- **Retry rate:** % of plans needing at least one auto-retry

---

## 10. Constraints & Assumptions

- v1 assumes structured/semi-structured, mostly-English data
- v1 assumes single-user, single-session context (no team accounts yet)
- LLM cost/latency means planning + validation reasoning uses the LLM, but bulk data manipulation always runs through deterministic code (pandas etc.), never through the LLM directly — this is a hard architectural rule, not an optimization
- File size/row limits will be enforced in MVP and raised over time

---

## 11. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM misclassifies user intent → wrong operation runs | Show plan before execution (or allow easy undo); validation step catches obviously wrong results |
| "Any data, any task" scope creep kills the MVP | Hard format/operation allow-list in v1; UI explicitly states what's supported |
| LLM tries to manipulate data directly (hallucinated numbers) | Architectural rule: LLM only plans/explains, tools execute; never let the model output "the answer" without it coming from real computation |
| Large files blow up cost/latency | Size limits + chunked/streamed processing + async job handling for big files |
| Sensitive data exposure | Sandboxing, per-session isolation, retention/deletion policy, no data used for training |
| Silent bad output erodes trust | Validation step is mandatory, not optional, on every run |

---

## 12. Rough Milestones (map directly to Antigravity "missions")

1. **M0 — Skeleton:** upload endpoint, format detection, basic profiling, "hello world" plan output (no execution yet)
2. **M1 — Cleaning loop end-to-end:** clean+dedupe+missing-values on CSV/Excel, with validation, download output
3. **M2 — Aggregation & charting:** group/sum/top-N + one chart type, plain-English summary
4. **M3 — Plan/validate/retry loop hardened:** auto-retry on validation failure, error explainability
5. **M4 — UI polish + format expansion (JSON, more chart types)**
6. **M5 (Phase 2 start):** PDF/DOCX extraction, stats & simple ML operations

See `flow.md` for the detailed step-by-step flow and `features.md` for the full phased feature breakdown.
