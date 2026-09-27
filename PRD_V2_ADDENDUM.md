# PRD V2 Addendum — Universal Format Scope Expansion

**Document status:** Official addendum to PRD.md  
**PRD.md version superseded:** v1 (original MVP scope)  
**Addendum date:** 2026-09-26  
**Author:** DataWise engineering team  

> This addendum intentionally supersedes specific non-goals stated in PRD.md's original
> scope without modifying PRD.md itself. PRD.md remains an accurate historical record of
> the v1 MVP scope. All v2 decisions live here.

---

## 1. New Goal: Universal, Extensible Multi-Format Processing

DataWise v2 aims to become a universal data-understanding assistant capable of
processing **any structured or semi-structured file type** that a user uploads, not
limited to CSV/Excel/JSON tabular data.

The v2 architecture introduces:
- A **file detection layer** (content-based, not extension-trusting) that categorises
  every incoming file.
- A **processor registry** that maps a detected file category to the appropriate
  processing pipeline.
- A **processor interface** (abstract base class) that every format processor must
  implement, ensuring consistent capability guarantees.
- An **honest capabilities manifest** (`capabilities.json`) that lists exactly which
  operations are supported right now (not aspirationally).

The key architectural insight is: the 5-stage pipeline built in Phases 1–8 does not
disappear — it becomes the **tabular processor**, the first concrete implementation of
the new interface. Every future format processor plugs into the same registry.

---

## 2. Prior Non-Goals That Are Now Superseded

The following statements from PRD.md §1 / §8 non-goals are superseded by this addendum:

| Original non-goal | Superseded because |
|---|---|
| "Not promising to handle 'any data of any kind'" | v2's explicit goal is universal format support with an extensible processor registry |
| "Scope: CSV, Excel, JSON tabular files only" | New processor categories: document, image, video, audio, archive, presentation (Phases 10–13) |
| "50 MB file size limit" | Application-level size limit removed; real constraint is available infrastructure RAM/disk, not a hardcoded cap |
| "500,000 row limit" | Application-level row limit removed; same infrastructure caveat applies |

---

## 3. Prior Constraints That Are ABSOLUTE and Non-Negotiable

The following constraints from PRD.md remain unchanged and are explicitly reinforced here.
**No future phase may override these:**

| Constraint | Why it remains |
|---|---|
| **No arbitrary code execution** (`eval`/`exec` on user data) | Security: this is an absolute constraint regardless of file type or "convenience" |
| **Allow-list tool registry** | Every supported operation must be explicitly registered; no dynamic dispatch from user input |
| **Session-isolated storage** | Every upload lives in its own UUID-scoped directory; no cross-session data access |
| **Path traversal prevention** | User-supplied filenames are NEVER used to construct filesystem paths |
| **No raw internal errors to UI** | Only structured, plain-language error messages reach the user |
| **Pydantic schema validation** | All inter-stage contracts remain validated by Pydantic v2 schemas |
| **Operation-specific validation** | Validator must assert WHAT CHANGED (the data is the evidence), not just THAT SOMETHING RAN |

---

## 4. Infrastructure Constraints That Still Apply (After Limit Removal)

Removing the *application-level* limits does not mean DataWise is "unlimited."
The following real constraints apply:

- **RAM**: Processing a DataFrame requires roughly 5–10× its on-disk compressed size in
  memory (pandas overhead). A 2 GB file on a 4 GB RAM server will OOM. This is a hosting
  constraint, not a DataWise constraint.
- **Disk**: Session directories must fit on the deployment disk. The session cleanup
  policy (workspace/sessions/) manages this.
- **Browser upload size**: The browser's HTTP layer and Streamlit's upload component have
  their own limits, independent of DataWise's Python code. The Streamlit
  `server.maxUploadSize` config setting must be set explicitly (default is 200 MB).
- **Processing time**: Very large files (>10M rows) may take minutes. No hard timeout is
  imposed at the application level, but hosting platforms impose their own request
  timeouts.

---

## 5. Phase Roadmap for Universal Format Support

| Phase | Category | Planned processor |
|---|---|---|
| 9 (this phase) | Architecture | Detection layer, processor registry, tabular refactor |
| 10 | Document | PDF, DOCX, TXT (text extraction, summarisation) |
| 11 | Image | JPEG, PNG, GIF, WEBP (visual description, metadata) |
| 12 | Audio | MP3, WAV, MP4-audio (transcription, duration, metadata) |
| 13 | Video | MP4, MOV (frame extraction, transcription, metadata) |
| 13 | Archive | ZIP, TAR (recursive detection and routing) |
| 13 | Presentation | PPTX (slide extraction) |

---

## 6. What PRD.md Still Documents Accurately

PRD.md continues to accurately describe:
- The user personas and problem statement (§1–§3)
- The functional requirements for tabular data (FR1–FR7)
- The 5-stage pipeline architecture (now the tabular processor)
- The security requirements (absolute, see §3 above)
- Phase 1–8 implementation history

---

*End of PRD_V2_ADDENDUM.md*
