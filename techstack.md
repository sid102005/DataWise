# techstack.md — DataWise

Guiding principle: **keep the MVP boring and simple**. Every choice below optimizes for "one developer (or one Antigravity agent) can build and debug this without complication," not for maximum scalability on day one.

---

## 0. The One Non-Negotiable Architectural Rule

> **The LLM plans and explains. It never touches the data directly.**

All actual data manipulation (cleaning, math, aggregation, ML) runs through deterministic, testable code (pandas/numpy/scikit-learn). The LLM's job is: read the data profile → understand intent → produce a step-by-step plan → (later) turn the executed plan into a plain-English summary. This single rule prevents the two biggest failure modes: hallucinated numbers, and unreviewable "black box" behavior.

---

## 1. MVP Stack (Phase 1)

| Layer | Recommendation | Why |
|---|---|---|
| **Frontend** | Streamlit (fastest) **or** Next.js + React (if you want a polished product UI) | Streamlit = a working UI in days, ideal for proving the loop. Next.js = better long-term if this becomes a real product. Pick Streamlit for MVP unless you already know React well. |
| **Backend / API** | FastAPI (Python) | Async support, automatic OpenAPI docs, pairs naturally with the Python data-science tool layer — no context-switching between languages. |
| **LLM provider** | Claude (Anthropic API) or Gemini API | Use for: intent parsing, plan generation, plain-English summaries, clarifying questions. Structured outputs (JSON) for the plan object. |
| **Agent orchestration** | Hand-rolled state machine (Understand → Plan → Execute → Validate → Deliver) rather than a heavy framework | For a well-defined 5-stage loop, a framework like LangChain/LlamaIndex adds complexity you don't need yet. A plain Python class with explicit stage functions is easier to debug, test, and reason about. Revisit a framework only if the plan/tool graph gets genuinely complex (Phase 2+). |
| **Tool layer (execution)** | pandas, numpy, openpyxl (Excel), python-dateutil | This is where the real work happens. Each "tool" is a small, pure, testable Python function (`drop_duplicates_by`, `impute_missing`, `groupby_aggregate`, etc.) that the planner's steps map onto 1:1. |
| **Charting** | matplotlib / plotly | Plotly if you want interactive charts in the UI; matplotlib is simpler if charts are just exported as images. |
| **Sandboxing** | Run tool-layer code in-process (it's your own trusted functions, not LLM-generated code) — **do not** let the LLM generate and `exec()` raw Python in MVP. If/when you do allow LLM-generated code (Phase 2+ for edge-case operations), sandbox it (e.g. `restrictedpython`, a subprocess with no network/file access, or a container). | Keeps MVP simple and safe. LLM-generated arbitrary code execution is a real security surface — defer it. |
| **File storage** | Local disk / temp storage per session (MVP) → move to S3-compatible object storage (Phase 2+) | Don't build cloud storage integration before you need it. |
| **Session/state** | In-memory or SQLite for MVP | No need for Postgres/Redis until you have real concurrent multi-user load. |
| **Validation layer** | Plain Python assertions/checks against the data profile before/after each step | No special library needed — this is just code that compares row counts, null counts, dtypes, and "does the expected output exist." |
| **Testing** | pytest | Unit-test every tool-layer function independently of the LLM (this is what makes the system trustworthy — the deterministic core is fully testable). |
| **Deployment (MVP)** | Single container (Docker) → Render / Railway / Fly.io / a single VM | No need for Kubernetes at MVP scale. |

---

## 2. Phase 2 Additions

| Need | Add |
|---|---|
| PDF/DOCX extraction | `pdfplumber` / `PyMuPDF` for PDFs, `python-docx` for Word |
| OCR (images/scanned docs) | `pytesseract` or a cloud OCR API (Google Vision / AWS Textract) |
| Simple ML (regression/classification) | scikit-learn — keep it to well-understood, explainable models (linear/logistic regression, decision trees, random forest) rather than deep learning, so results stay explainable |
| Report generation | Jinja2 templates → rendered to PDF (e.g. via `weasyprint`) or DOCX |
| Bigger files / async jobs | Move heavy jobs to a background worker (Celery + Redis, or a simple task queue) so the API isn't blocked |
| Object storage | S3 / GCS for uploaded files and results |
| Database | Postgres for session history, saved pipelines, user accounts |

## 3. Phase 3 Additions

| Need | Add |
|---|---|
| Live data sources | DB connectors (SQLAlchemy), REST API ingestion |
| Scheduled jobs | Simple cron-based scheduler → Airflow/Prefect only if pipeline complexity justifies it |
| Multi-user / auth | Auth provider (Clerk/Auth0/Supabase Auth) + Postgres-backed accounts |
| Public developer API | Versioned FastAPI routes + API key auth + rate limiting |
| Vector search (if adding "chat with your data over time") | pgvector or a managed vector DB — only if you add semantic search over past datasets/results |

---

## 4. What to Deliberately Avoid in v1

- ❌ A heavyweight agent framework before you need one — the 5-stage loop is simple enough to hand-code and debug
- ❌ Letting the LLM execute arbitrary generated code against real user data
- ❌ Microservices — one FastAPI service is enough until there's a real scaling reason
- ❌ Kubernetes / complex infra before there's real traffic
- ❌ Training your own ML models — use well-understood pre-built algorithms only
- ❌ Promising "any file type" support in the code or UI — keep the supported-format list explicit and enforced

---

## 5. Suggested Repo Structure

```
datawise/
├── backend/
│   ├── api/                # FastAPI routes
│   ├── core/
│   │   ├── understanding.py    # Stage 1: format/schema/profile detection
│   │   ├── intent.py           # Stage 2: LLM prompt → objectives
│   │   ├── planner.py          # Stage 3: objectives → step list
│   │   ├── executor.py         # Stage 4: runs steps via tools/
│   │   ├── validator.py        # Stage 5: checks results
│   │   └── output.py           # builds file/table/chart/summary
│   ├── tools/               # pure, tested functions: clean.py, transform.py,
│   │                         # aggregate.py, stats.py, ml.py, chart.py
│   ├── models/               # Pydantic schemas: DataProfile, Objective, Plan, Step, ValidationResult
│   └── tests/
├── frontend/                 # Streamlit app or Next.js app
├── PRD.md
├── flow.md
├── techstack.md
└── features.md
```

This structure keeps the five stages as five clearly separated modules — which also makes it straightforward to hand each one to Antigravity as its own milestone/mission.
