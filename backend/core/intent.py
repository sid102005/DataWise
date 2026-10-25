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

import json
import logging
import re
from typing import Any

from backend.models.schemas import DataProfile, InferredType, Objective, ObjectiveCategory

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword → ObjectiveCategory mapping for deterministic fallback
# ---------------------------------------------------------------------------
_KEYWORD_MAP: list[tuple[re.Pattern[str], ObjectiveCategory]] = [
    (re.compile(
        r"\b(clean|dedupe|duplicate|duplicates|missing|null|nulls|impute|fix|standardiz\w*|"
        r"ml[\s-]?ready|machine[\s-]?learning|prepare\s+for\s+ml|data[\s-]?prep|preprocess)\b",
        re.I,
    ), ObjectiveCategory.CLEAN),
    (re.compile(r"\b(group|grouping|aggregat\w*|sum|average|avg|count|min|max|total)\b", re.I), ObjectiveCategory.AGGREGATE),
    (re.compile(r"\b(sort|rank|top[\s-]?\d+|bottom[\s-]?\d+|highest|lowest|largest|smallest)\b", re.I), ObjectiveCategory.AGGREGATE),
    (re.compile(r"\b(chart|plot|graph|visuali[sz]\w*|bar|line|pie)\b", re.I), ObjectiveCategory.VISUALIZE),
    # "only" kept for filter-style prompts ("only Region = East"); select extractors run first.
    (re.compile(r"\b(filter|where|only|exclude|keep|remove row)\b", re.I), ObjectiveCategory.TRANSFORM),
    (re.compile(r"\b(rename|reorder|add column|derive|calculate|compute|select column|display column)\b", re.I), ObjectiveCategory.TRANSFORM),
    (re.compile(r"\b(correlat\w*|distribut\w*|stat\w*|mean|median|std|outlier\w*)\b", re.I), ObjectiveCategory.STAT),
    (re.compile(
        r"\b(extract|pull|find|list|show me|ocr|heading|outline|table|tables|"
        r"metadata|entity|entities|invoice|redact|pii|mention|language|page)\b",
        re.I,
    ), ObjectiveCategory.EXTRACT),
    (re.compile(r"\b(report|summary|summariz\w*|overview|tldr|abstract)\b", re.I), ObjectiveCategory.REPORT),
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
    if not profile.columns:
        return []

    col_map = {c.name.lower(): c.name for c in profile.columns}
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
                                f"available: {', '.join(c.name for c in (profile.columns or []))}"
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
                            f"available: {', '.join(c.name for c in (profile.columns or []))}"
                        ),
                        target_columns=[],
                    )
                )

    return objectives


def _extract_select_operations(prompt: str, profile: DataProfile) -> list[Objective]:
    """Extract column-projection intents (keep/show/display/select columns)."""
    if not profile.columns:
        return []

    text = prompt.strip()
    col_map = {c.name.lower(): c.name for c in profile.columns}
    col_names = [c.name for c in profile.columns]

    # "only display/show/keep 2 columns" / "display only 2 columns"
    m_count = re.search(
        r"\b(?:only\s+)?(?:display|show|keep|select|project)\s+(?:only\s+)?(\d+)\s+columns?\b"
        r"|\b(?:display|show|keep|select)\s+only\s+(\d+)\s+columns?\b"
        r"|\bonly\s+(\d+)\s+columns?\b",
        text,
        re.I,
    )
    if m_count:
        count = int(next(g for g in m_count.groups() if g is not None))
        return [
            Objective(
                category=ObjectiveCategory.TRANSFORM,
                description=f"select_columns_first: {count}",
                target_columns=col_names[:count],
                parameters={"count": count},
            )
        ]

    # Named columns: "show only Name and Age", "keep columns Name, Age",
    # "select Name, Age columns", "display only the Name and Age columns"
    m_named = re.search(
        r"\b(?:show|display|keep|select|project|include)\s+"
        r"(?:only\s+)?(?:the\s+)?(?:columns?\s+)?"
        r"(.+?)"
        r"(?:\s+columns?)?\s*$",
        text,
        re.I,
    )
    # Also: "only columns Name and Age" / "only Name and Age columns"
    if not m_named:
        m_named = re.search(
            r"\bonly\s+(?:the\s+)?(?:columns?\s+)?(.+?)(?:\s+columns?)?\s*$",
            text,
            re.I,
        )

    if m_named:
        raw = m_named.group(1).strip()
        # Skip if this looks like a filter condition (has comparison ops)
        if re.search(r"[<>=]|where\b", raw, re.I):
            return []
        # Skip pure count-like leftovers
        if re.fullmatch(r"\d+", raw):
            return []

        # Split on commas / "and" / "&"
        parts = re.split(r"\s*(?:,|&|\band\b)\s*", raw, flags=re.I)
        resolved: list[str] = []
        for part in parts:
            token = re.sub(
                r"\b(the|column|columns|field|fields|of)\b",
                " ",
                part,
                flags=re.I,
            ).strip(" \t\"'")
            if not token:
                continue
            actual = _fuzzy_match_column(token, col_map)
            if actual and actual not in resolved:
                resolved.append(actual)

        if resolved:
            return [
                Objective(
                    category=ObjectiveCategory.TRANSFORM,
                    description=f"select_columns: {', '.join(resolved)}",
                    target_columns=resolved,
                )
            ]

    return []


def _extract_aggregate_operations(prompt: str, profile: DataProfile) -> list[Objective]:
    """Extract structured sort / top-N / groupby intents."""
    if not profile.columns:
        return []

    text = prompt.strip()
    col_map = {c.name.lower(): c.name for c in profile.columns}
    typed_numeric = [c.name for c in profile.columns if c.inferred_type == InferredType.NUMERIC]
    id_like = {c.name for c in profile.columns if c.inferred_type == InferredType.ID}

    # group by X and sum/avg/count Y
    gm = re.search(
        r"\bgroup(?:\s*by)?\s+([A-Za-z0-9_]+)\b.*?\b(sum|avg|average|mean|count|min|max)\b\s+([A-Za-z0-9_]+)",
        text,
        re.I,
    )
    if gm:
        by_raw, agg_raw, metric_raw = gm.groups()
        by_col = _fuzzy_match_column(by_raw, col_map) or by_raw
        metric_col = _fuzzy_match_column(metric_raw, col_map) or metric_raw
        agg = "mean" if agg_raw.lower() in {"avg", "average"} else agg_raw.lower()
        return [
            Objective(
                category=ObjectiveCategory.AGGREGATE,
                description=f"groupby: {by_col} | metric: {metric_col} | agg: {agg}",
                target_columns=[by_col, metric_col],
                parameters={"by": by_col, "metric": metric_col, "agg": agg},
            )
        ]

    # top / bottom N
    tm = re.search(r"\b(top|bottom)[\s-]?(\d+)\b", text, re.I)
    if tm:
        direction = "descending" if tm.group(1).lower() == "top" else "ascending"
        n_val = int(tm.group(2))
        # optional "by Col"
        by_m = re.search(r"\bby\s+([A-Za-z0-9_]+)", text, re.I)
        col = _fuzzy_match_column(by_m.group(1), col_map) if by_m else None
        if not col:
            col = next((c for c in typed_numeric if c not in id_like), typed_numeric[0] if typed_numeric else None)
        if col:
            return [
                Objective(
                    category=ObjectiveCategory.AGGREGATE,
                    description=f"sort_column: {col} {direction}",
                    target_columns=[col],
                    parameters={"column": col, "ascending": direction == "ascending"},
                ),
                Objective(
                    category=ObjectiveCategory.AGGREGATE,
                    description=f"top_n: {n_val}",
                    target_columns=[col],
                    parameters={"n": n_val},
                ),
            ]

    # sort [by Col] [asc/desc]
    if re.search(r"\b(sort|order\s+by|rank)\b", text, re.I):
        by_m = re.search(r"\b(?:sort|order|rank)\b.*?\bby\s+([A-Za-z0-9_]+)", text, re.I)
        col = _fuzzy_match_column(by_m.group(1), col_map) if by_m else None
        if not col:
            # column named anywhere in the prompt
            for name, actual in col_map.items():
                if re.search(rf"\b{re.escape(name)}\b", text, re.I):
                    col = actual
                    break
        if not col:
            col = next((c for c in typed_numeric if c not in id_like), typed_numeric[0] if typed_numeric else None)
        if not col and profile.columns:
            col = profile.columns[0].name

        if col:
            if re.search(r"\b(desc|descending|highest|largest)\b", text, re.I):
                direction = "descending"
            elif re.search(r"\b(asc|ascending|lowest|smallest)\b", text, re.I):
                direction = "ascending"
            else:
                direction = "ascending"
            return [
                Objective(
                    category=ObjectiveCategory.AGGREGATE,
                    description=f"sort_column: {col} {direction}",
                    target_columns=[col],
                    parameters={"column": col, "ascending": direction == "ascending"},
                )
            ]

    return []


def _parse_deterministic(prompt: str, profile: DataProfile) -> list[Objective]:
    """Rule-based fallback parser. Returns at least one Objective."""

    # 1. Try structured column-operation extraction first
    col_ops = _extract_column_operations(prompt, profile)
    if col_ops:
        return col_ops

    # 2. Column projection (select / show only / display N columns)
    select_ops = _extract_select_operations(prompt, profile)
    if select_ops:
        return select_ops

    # 3. Sort / top-N / groupby
    agg_ops = _extract_aggregate_operations(prompt, profile)
    if agg_ops:
        return agg_ops

    # 4. General keyword → category mapping
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


def _parse_with_llm(
    prompt: str,
    profile: DataProfile,
    llm_client: Any,
) -> list[Objective] | None:
    """Attempt LLM-backed intent parsing with strict Pydantic validation."""
    if not hasattr(llm_client, "generate_structured"):
        return None

    columns_summary = [
        {"name": c.name, "type": c.inferred_type.value, "null_count": c.null_count}
        for c in (profile.columns or [])
    ]

    system_prompt = (
        "You are the DataWise Intent Parser. Translate the user's natural language data instruction "
        "into an ordered list of discrete, structured objectives.\n\n"
        "Allowed Objective categories:\n"
        "- clean: remove duplicates, handle missing values, standardize formats\n"
        "- transform: filter rows, drop/rename/add columns, change types\n"
        "- aggregate: groupby summaries, sort, top-N ranking\n"
        "- visualize: charts (bar, line, pie)\n"
        "- stat: statistical correlations, distributions\n"
        "- extract: text or table extraction\n"
        "- compare: compare datasets or groups\n"
        "- report: summary report generation\n\n"
        "Respond ONLY with a valid JSON object matching:\n"
        "{\n"
        '  "objectives": [\n'
        '    {\n'
        '      "category": "clean|transform|aggregate|visualize|stat|extract|compare|report",\n'
        '      "description": "Clear explanation of what this objective does",\n'
        '      "target_columns": ["col1", "col2"],\n'
        '      "parameters": {"key": "value"}\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    user_content = (
        f"User instruction: \"{prompt}\"\n\n"
        f"Dataset format: {profile.file_format}\n"
        f"Available columns: {json.dumps(columns_summary)}\n"
        f"Row count: {getattr(profile, 'row_count', 'unknown')}"
    )

    try:
        data = llm_client.generate_structured(
            prompt=user_content,
            system_prompt=system_prompt,
        )
        raw_objs = data.get("objectives", [])
        if not raw_objs and isinstance(data, list):
            raw_objs = data

        parsed_objectives: list[Objective] = []
        for item in raw_objs:
            if isinstance(item, dict):
                cat_str = str(item.get("category", "")).lower().strip()
                try:
                    category = ObjectiveCategory(cat_str)
                except ValueError:
                    category = ObjectiveCategory.CLEAN

                params = item.get("parameters") or {}
                if not isinstance(params, dict):
                    params = {}

                # Filter target_columns to valid strings
                cols = [str(c) for c in item.get("target_columns", []) if isinstance(c, (str, int, float))]

                parsed_objectives.append(
                    Objective(
                        category=category,
                        description=str(item.get("description", prompt[:120])),
                        target_columns=cols,
                        parameters=params,
                    )
                )
        if parsed_objectives:
            return parsed_objectives
    except Exception as exc:
        log.warning("LLM intent parsing failed, falling back to deterministic: %s", exc)

    return None


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

    # Track budget when LLM path is active (required for budget tests)
    if llm_client is not None and llm_call_counter is not None:
        llm_call_counter("parse_intent")

    # LLM-backed structured intent parsing path
    if llm_client is not None:
        llm_objs = _parse_with_llm(prompt, profile, llm_client)
        if llm_objs:
            return llm_objs

    return _parse_deterministic(prompt, profile)
