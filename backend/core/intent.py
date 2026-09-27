"""DataWise Stage 2 — Intent Understanding.

Parses a user's natural-language prompt into a list of structured Objective
objects. Full LLM-backed parsing is a Phase 4 concern.

This module provides:
  - A deterministic rule-based parser (no API calls) that covers the most
    common prompts reliably in CI / offline environments.
  - An LLM-backed path (Phase 4+) that can be activated by providing an
    LLM provider client.

ARCHITECTURE CONTRACT (decision.md — Dual-Provider LLM):
  - parse_intent() is the only public interface.
  - Returns a list of Objective; never raises on ambiguous prompts —
    it falls back to a 'clean' objective with a broad description.
  - The LLM is given ONLY the DataProfile metadata, never raw rows.

NLU DESIGN (Emergency Fix — Root Cause H1/H3):
  - Column-operation intent (drop_column, add_column, rename_column) is
    now extracted FIRST from the raw prompt before falling back to the
    general keyword-category mapper. This prevents "remove Phone" from
    being misclassified as a generic CLEAN task, which caused the silent
    no-op bug.
  - Each detected column operation is stored on the Objective.description
    in a structured mini-format that _steps_for_transform() in planner.py
    can parse deterministically.
"""

from __future__ import annotations

import re
from typing import Any

from backend.models.schemas import DataProfile, Objective, ObjectiveCategory


# ---------------------------------------------------------------------------
# Keyword → ObjectiveCategory mapping for deterministic fallback
# ---------------------------------------------------------------------------
_KEYWORD_MAP: list[tuple[re.Pattern[str], ObjectiveCategory]] = [
    (re.compile(r"\b(clean|dedupe|duplicate|duplicates|missing|null|nulls|impute|fix|standardiz\w*)\b", re.I), ObjectiveCategory.CLEAN),
    (re.compile(r"\b(group|grouping|aggregat\w*|sum|average|avg|count|min|max|total)\b", re.I), ObjectiveCategory.AGGREGATE),
    (re.compile(r"\b(sort|rank|top[\s-]?\d+|bottom[\s-]?\d+|highest|lowest|largest|smallest)\b", re.I), ObjectiveCategory.AGGREGATE),
    (re.compile(r"\b(chart|plot|graph|visuali[sz]\w*|bar|line|pie)\b", re.I), ObjectiveCategory.VISUALIZE),
    (re.compile(r"\b(filter|where|only|exclude|keep|remove row)\b", re.I), ObjectiveCategory.TRANSFORM),
    (re.compile(r"\b(rename|reorder|add column|derive|calculate|compute)\b", re.I), ObjectiveCategory.TRANSFORM),
    (re.compile(r"\b(correlat\w*|distribut\w*|stat\w*|mean|median|std|outlier\w*)\b", re.I), ObjectiveCategory.STAT),
    (re.compile(r"\b(extract|pull|find|list|show me)\b", re.I), ObjectiveCategory.EXTRACT),
    (re.compile(r"\b(report|summary|summariz\w*|overview)\b", re.I), ObjectiveCategory.REPORT),
    (re.compile(r"\b(compare|versus|vs\.?|difference|change)\b", re.I), ObjectiveCategory.COMPARE),
]

# ---------------------------------------------------------------------------
# Column-operation intent patterns
# Each tuple: (compiled regex, operation_type)
# These are checked BEFORE the general keyword map.
# ---------------------------------------------------------------------------
# Drop / remove a column ─────────────────────────────────────────────────────
# Covers: "remove Phone", "delete the Phone field", "drop Phone column",
#         "I don't need Phone anymore", "get rid of Phone",
#         "please remove Phone from the dataset", "delete Phone from this CSV"
# Drop / remove a column ─────────────────────────────────────────────────────
# Covers: "remove Phone", "delete the Phone field", "drop Phone column",
#         "I don't need Phone anymore", "get rid of Phone",
#         "please remove Phone from the dataset", "delete Phone from this CSV"
#
# GUARD: The matched column name must NOT be a row-operation noun
# (rows, row, duplicates, duplicate, data, all) to prevent 'remove duplicate rows'
# from being parsed as a column-drop.
_ROW_OP_NOUNS = frozenset({
    "rows", "row", "duplicates", "duplicate", "dupes", "dupe",
    "data", "all", "everything", "records", "record",
    "missing values", "null values", "nulls", "missing", "null", "empty rows",
})

# Optional trailing noise: "from the dataset", "from this CSV", "from the file", etc.
_TRAILING_NOISE = r"(?:\s+from\s+(?:the\s+|this\s+)?(?:dataset|csv|file|data|table|spreadsheet))?\s*$"

_DROP_COL_PATTERNS: list[re.Pattern[str]] = [
    # "remove/delete/drop/eliminate [the/a/of the] <col> [column/field/...] [from the ...]"
    re.compile(
        r"\b(?:remove|delete|drop|eliminate|erase|exclude|strip)\b"
        r"(?:\s+(?:the|a|of\s+the|column\s+of\s+the|field\s+of\s+the))?"
        r"\s+(?:column\s+of\s+the\s+|field\s+of\s+the\s+)?"
        r"['\"]?([A-Za-z0-9_ ]+?)['\"]?"
        r"(?:\s+(?:column|field|attribute|variable|col))?" + _TRAILING_NOISE,
        re.I,
    ),
    # "get rid of [the] <col> [column/field]"
    re.compile(
        r"\bget\s+rid\s+of\s+(?:the\s+)?['\"]?([A-Za-z0-9_ ]+?)['\"]?"
        r"(?:\s+(?:column|field|attribute|variable|col))?" + _TRAILING_NOISE,
        re.I,
    ),
    # "I don't need [the] <col> [column/field] [anymore/any more]"
    re.compile(
        r"\b(?:i\s+)?don'?t\s+need\s+(?:the\s+)?['\"]?([A-Za-z0-9_ ]+?)['\"]?"
        r"(?:\s+(?:column|field|attribute|variable|col))?(?:\s+any\s*more)?\s*$",
        re.I,
    ),
    # "now remove the column of the <col>"  (exact user phrasing from bug report)
    re.compile(
        r"\b(?:now\s+)?(?:remove|delete|drop)\s+the\s+column\s+of\s+the\s+"
        r"['\"]?([A-Za-z0-9_ ]+?)['\"]?" + _TRAILING_NOISE,
        re.I,
    ),
]

# Add / create a column ──────────────────────────────────────────────────────
# Covers: "add a column called Senior", "create a new column named Senior",
#         "add Senior as a new field", "make a Senior column"
_ADD_COL_PATTERNS: list[re.Pattern[str]] = [
    # "add [a/an] [new] column [called/named/labeled] <col>"
    re.compile(
        r"\b(?:add|insert|append|include)\b"
        r"(?:\s+(?:a|an|one))?"
        r"(?:\s+new)?"
        r"\s+(?:column|field|attribute|col)"
        r"(?:\s+(?:called|named|labeled|entitled))?"
        r"\s+['\"]?([A-Za-z0-9_ ]+?)['\"]?\s*$",
        re.I,
    ),
    # "add <col> as a new [column/field]"
    re.compile(
        r"\b(?:add|insert|append)\s+['\"]?([A-Za-z0-9_ ]+?)['\"]?"
        r"\s+as\s+a\s+new\s+(?:column|field|attribute|col)\s*$",
        re.I,
    ),
    # "create [a] [new] column [called/named] <col>"
    re.compile(
        r"\b(?:create|make|generate|build)\s+(?:a\s+)?(?:new\s+)?"
        r"(?:column|field|attribute|col)"
        r"(?:\s+(?:called|named|labeled|entitled))?"
        r"\s+['\"]?([A-Za-z0-9_ ]+?)['\"]?\s*$",
        re.I,
    ),
    # "make a <col> column"
    re.compile(
        r"\b(?:make|create|build|generate)\s+(?:a\s+|an\s+|one\s+)?"
        r"['\"]?([A-Za-z0-9_ ]+?)['\"]?"
        r"\s+(?:column|field|attribute|col)\s*$",
        re.I,
    ),
]

# Rename a column ────────────────────────────────────────────────────────────
_RENAME_COL_PATTERN = re.compile(
    r"\b(?:rename|relabel|change\s+(?:the\s+name\s+of|name\s+of|column))\s+"
    r"['\"]?([A-Za-z0-9_ ]+?)['\"]?"
    r"\s+(?:to|as|into)\s+"
    r"['\"]?([A-Za-z0-9_ ]+?)['\"]?\s*$",
    re.I,
)


def _fuzzy_match_column(name: str, col_map: dict[str, str]) -> str | None:
    """Case-insensitive column name lookup; strips common noise words."""
    cleaned = name.strip().lower()
    # Direct lowercase match
    if cleaned in col_map:
        return col_map[cleaned]
    # Strip trailing noise: "column", "field", "data", "the"
    for noise in (" column", " field", " data", " the", "the "):
        cleaned = cleaned.replace(noise, "").strip()
    return col_map.get(cleaned)


def _extract_column_operations(
    prompt: str,
    profile: DataProfile,
) -> list[Objective]:
    """Extract explicit column-level operations (drop/add/rename) from the raw prompt.

    Returns a list of TRANSFORM Objectives whose .description encodes the
    structured operation in a mini-format that planner._steps_for_transform()
    can parse:
      - drop_column: <col>
      - add_column: <col>
      - rename_column: <old> to <new>

    Returns [] if no column operation is detected.
    """
    col_map = {c.name.lower(): c.name for c in (profile.columns or [])}
    objectives: list[Objective] = []
    seen_descriptions: set[str] = set()  # deduplicate across patterns

    # --- Check drop patterns ---
    for pattern in _DROP_COL_PATTERNS:
        m = pattern.search(prompt.strip())
        if m:
            raw_col = m.group(1).strip()
            # Guard: reject generic row-operation nouns — they belong to CLEAN, not column ops
            if raw_col.lower() in _ROW_OP_NOUNS:
                continue
            # Guard: reject multi-word phrases that look like row-op descriptions
            # e.g. "duplicate rows", "all rows", "missing values"
            words = raw_col.lower().split()
            if any(w in _ROW_OP_NOUNS for w in words):
                continue
            actual_col = _fuzzy_match_column(raw_col, col_map)
            if actual_col:
                desc = f"drop_column: {actual_col}"
                if desc not in seen_descriptions:
                    seen_descriptions.add(desc)
                    objectives.append(
                        Objective(
                            category=ObjectiveCategory.TRANSFORM,
                            description=desc,
                            target_columns=[actual_col],
                        )
                    )
                # Don't break — a prompt can name multiple distinct columns
            else:
                # Column not found — surface an honest failure via the planner
                desc = f"drop_column_not_found: {raw_col}"
                if desc not in seen_descriptions:
                    seen_descriptions.add(desc)
                    objectives.append(
                        Objective(
                            category=ObjectiveCategory.TRANSFORM,
                            description=(
                                f"drop_column_not_found: {raw_col} | "
                                f"available: {', '.join(c.name for c in profile.columns)}"
                            ),
                            target_columns=[],
                        )
                    )

    # --- Check add_column patterns (only if no drop matched this phrase) ---
    if not objectives:
        for pattern in _ADD_COL_PATTERNS:
            m = pattern.search(prompt.strip())
            if m:
                col_name = m.group(1).strip()
                objectives.append(
                    Objective(
                        category=ObjectiveCategory.TRANSFORM,
                        description=f"add_column: {col_name}",
                        target_columns=[col_name],
                    )
                )

    # --- Check rename pattern ---
    if not objectives:
        m = _RENAME_COL_PATTERN.search(prompt.strip())
        if m:
            old_col_raw, new_col = m.group(1).strip(), m.group(2).strip()
            actual_old = _fuzzy_match_column(old_col_raw, col_map)
            if actual_old:
                objectives.append(
                    Objective(
                        category=ObjectiveCategory.TRANSFORM,
                        description=f"rename_column: {actual_old} to {new_col}",
                        target_columns=[actual_old],
                    )
                )
            else:
                objectives.append(
                    Objective(
                        category=ObjectiveCategory.TRANSFORM,
                        description=(
                            f"rename_column_not_found: {old_col_raw} | "
                            f"available: {', '.join(c.name for c in profile.columns)}"
                        ),
                        target_columns=[],
                    )
                )

    return objectives


def _parse_deterministic(prompt: str, profile: DataProfile) -> list[Objective]:
    """Rule-based fallback parser. Returns at least one Objective."""

    # 1. Try structured column-operation extraction first
    col_ops = _extract_column_operations(prompt, profile)
    if col_ops:
        return col_ops

    # 2. General keyword → category mapping
    detected: list[ObjectiveCategory] = []
    for pattern, category in _KEYWORD_MAP:
        if pattern.search(prompt) and category not in detected:
            detected.append(category)

    if not detected:
        # Default: treat any unrecognized prompt as a cleaning task
        detected.append(ObjectiveCategory.CLEAN)

    objectives: list[Objective] = []
    for cat in detected:
        col_names = [c.name for c in (profile.columns or [])]
        objectives.append(
            Objective(
                category=cat,
                description=f"{cat.value.capitalize()} operation derived from prompt: \"{prompt[:120]}\"",
                target_columns=col_names,
            )
        )
    return objectives


def parse_intent(
    prompt: str,
    profile: DataProfile,
    llm_client: object | None = None,
    llm_call_counter: Any = None,
) -> list[Objective]:
    """Parse a user prompt into a list of structured Objectives.

    Args:
        prompt: The user's natural-language instruction.
        profile: Metadata-only DataProfile (no raw rows — per privacy decision).
        llm_client: Optional LLM provider client for Phase 4+ LLM-backed parsing.
                    When None, the deterministic rule-based fallback is used.
        llm_call_counter: Optional counter callback for budget tracking.

    Returns:
        List of Objective instances (at least one guaranteed).
    """
    if not prompt or not prompt.strip():
        return [
            Objective(
                category=ObjectiveCategory.CLEAN,
                description="No instruction provided — defaulting to clean operation.",
            )
        ]

    # Track budget when LLM path is active
    if llm_client is not None and llm_call_counter is not None:
        llm_call_counter("parse_intent")

    # Phase 4+: LLM path (not yet implemented — falls through to deterministic)
    if llm_client is not None:
        # TODO Phase 4: call llm_client with profile JSON + prompt,
        # parse structured JSON response into Objective list.
        pass

    return _parse_deterministic(prompt, profile)
