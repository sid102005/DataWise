"""DataWise Stage 3 — Task Planner.

Converts a list of Objectives (from Stage 2) and a DataProfile (from Stage 1)
into an ordered, inspectable Plan whose Steps map 1:1 to registered tool-layer
functions.

Full LLM-backed planning is a Phase 4 concern. This module provides:
  - A deterministic heuristic planner that generates Plans from Objectives
    using the DataProfile metadata to choose sensible defaults.
  - A stub LLM path (Phase 4+) activated by providing an llm_client.

ARCHITECTURE CONTRACT:
  - create_plan() is the only public interface.
  - revise_plan() adjusts a previously-failed plan; used by pipeline.py's
    retry loop — never called from executor.py or validator.py.
  - Plans are inspectable Pydantic objects (logged as the audit trail).
  - The LLM is given ONLY metadata — never raw rows.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

log = logging.getLogger(__name__)

from backend.models.schemas import (
    ClarificationRequest,
    DataProfile,
    InferredType,
    Objective,
    ObjectiveCategory,
    Plan,
    Step,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Heuristic planner helpers
# ---------------------------------------------------------------------------


def _numeric_columns(profile: DataProfile) -> list[str]:
    return [c.name for c in (profile.columns or []) if c.inferred_type == InferredType.NUMERIC]


def _date_columns(profile: DataProfile) -> list[str]:
    return [c.name for c in (profile.columns or []) if c.inferred_type == InferredType.DATE]


def _columns_with_nulls(profile: DataProfile) -> list[str]:
    return [c.name for c in (profile.columns or []) if c.null_count > 0]


def _id_columns(profile: DataProfile) -> list[str]:
    return [c.name for c in (profile.columns or []) if c.inferred_type == InferredType.ID]


def _steps_for_clean(profile: DataProfile, step_offset: int) -> list[Step]:
    """Generate cleaning steps grounded in the actual DataProfile."""
    steps: list[Step] = []
    n = step_offset

    if profile.file_format in {"pdf", "docx", "txt", "md"}:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_text",
            description="Extract text from document.",
            parameters={},
            expected_output="Text extracted from document.",
        ))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="clean_text",
            description="Normalize whitespace in extracted text.",
            parameters={},
            expected_output="Whitespace normalized.",
        ))
        return steps

    if profile.file_format in {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"}:
        return _steps_for_image([], profile, step_offset)

    if profile.file_format in {"wav", "mp3"}:
        return _steps_for_audio([], profile, step_offset)

    # Deduplication — only if duplicates actually exist
    id_cols = _id_columns(profile)
    if profile.duplicate_row_count > 0:
        params: dict[str, Any] = {}
        if id_cols:
            params["subset"] = id_cols[0] if len(id_cols) == 1 else id_cols
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="drop_duplicates",
            description=f"Remove {profile.duplicate_row_count} duplicate row(s).",
            parameters=params,
            expected_output="Duplicate rows removed; row count reduced.",
        ))

    # Handle missing values — only for columns that actually have nulls
    null_cols = _columns_with_nulls(profile)
    if null_cols:
        for col in null_cols:
            col_info = next(c for c in profile.columns if c.name == col)
            strategy = "median" if col_info.inferred_type == InferredType.NUMERIC else "mode"
            n += 1
            steps.append(Step(
                step_number=n,
                tool_name="handle_missing",
                description=f"Fill {col_info.null_count} missing value(s) in '{col}' using {strategy}.",
                parameters={"columns": col, "strategy": strategy},
                expected_output=f"No nulls remain in '{col}'.",
            ))

    # Standardize dates — only if date columns exist
    date_cols = _date_columns(profile)
    for col in date_cols:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="standardize_dates",
            description=f"Standardize date format in '{col}' to ISO YYYY-MM-DD.",
            parameters={"column": col, "target_format": "%Y-%m-%d"},
            expected_output=f"'{col}' contains uniformly formatted dates.",
        ))

    return steps


def _pick_rank_column(objectives: list[Objective], profile: DataProfile) -> str | None:
    """Choose a numeric column for sort/top-N, preferring names mentioned in objectives."""
    numeric_cols = _numeric_columns(profile)
    id_names = {c.lower() for c in _id_columns(profile)}
    col_map = {c.name.lower(): c.name for c in (profile.columns or [])}

    for obj in objectives:
        # Structured: sort_column: <col> ...
        m = re.match(r"sort_column:\s*([A-Za-z0-9_]+)", obj.description, re.I)
        if m:
            named = col_map.get(m.group(1).lower())
            if named:
                return named
        for c in numeric_cols:
            if c.lower() not in id_names and re.search(rf"\b{re.escape(c)}\b", obj.description, re.I):
                return c
        for c in (profile.columns or []):
            if re.search(rf"\b{re.escape(c.name)}\b", obj.description, re.I):
                return c.name

    return next(
        (c for c in numeric_cols if c.lower() not in id_names),
        numeric_cols[0] if numeric_cols else None,
    )


def _parse_sort_direction(text: str) -> bool:
    """Return True for ascending, False for descending. Default: ascending for bare sort."""
    if re.search(r"\b(desc|descending|highest|largest|top)\b", text, re.I):
        return False
    if re.search(r"\b(asc|ascending|lowest|smallest|bottom)\b", text, re.I):
        return True
    return True


def _steps_for_aggregate(
    objectives: list[Objective],
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate groupby / sort / top-N steps from aggregate objectives.

    Structured descriptions from intent.py:
      - groupby: <col> | metric: <col> | agg: <fn>
      - sort_column: <col> ascending|descending
      - top_n: <n> [by <col>] [ascending|descending]
    """
    steps: list[Step] = []
    n = step_offset
    col_map = {c.name.lower(): c.name for c in (profile.columns or [])}
    full_text = " ".join(o.description for o in objectives)

    # ── Structured groupby ────────────────────────────────────────────────
    for obj in objectives:
        gm = re.match(
            r"groupby:\s*([A-Za-z0-9_]+)\s*\|\s*metric:\s*([A-Za-z0-9_]+)\s*\|\s*agg:\s*([A-Za-z]+)",
            obj.description,
            re.I,
        )
        if gm:
            by_raw, metric_raw, agg = gm.group(1), gm.group(2), gm.group(3).lower()
            by_col = col_map.get(by_raw.lower(), by_raw)
            metric_col = col_map.get(metric_raw.lower(), metric_raw)
            n += 1
            steps.append(Step(
                step_number=n,
                tool_name="groupby_aggregate",
                description=f"Group by '{by_col}' and {agg} '{metric_col}'.",
                parameters={"by": by_col, "metric": metric_col, "agg": agg},
                expected_output=f"One row per '{by_col}' with {agg} of '{metric_col}'.",
            ))
            return steps

    # Legacy free-text groupby: "group by Region and sum Sales"
    legacy_gb = re.search(
        r"\bgroup(?:\s*by)?\s+([A-Za-z0-9_]+)\b.*?\b(sum|avg|average|mean|count|min|max)\b\s+([A-Za-z0-9_]+)",
        full_text,
        re.I,
    )
    if legacy_gb:
        by_raw, agg_raw, metric_raw = legacy_gb.groups()
        agg = "mean" if agg_raw.lower() in {"avg", "average"} else agg_raw.lower()
        by_col = col_map.get(by_raw.lower(), by_raw)
        metric_col = col_map.get(metric_raw.lower(), metric_raw)
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="groupby_aggregate",
            description=f"Group by '{by_col}' and {agg} '{metric_col}'.",
            parameters={"by": by_col, "metric": metric_col, "agg": agg},
            expected_output=f"One row per '{by_col}' with {agg} of '{metric_col}'.",
        ))
        return steps

    # ── Top-N (explicit) — sort then truncate ─────────────────────────────
    top_n_val: int | None = None
    for obj in objectives:
        m = re.search(r"(?:top_n:\s*|top[\s-]?)(\d+)\b", obj.description, re.I)
        if m:
            top_n_val = int(m.group(1))
            break
        m = re.search(r"\bbottom[\s-]?(\d+)\b", obj.description, re.I)
        if m:
            top_n_val = int(m.group(1))
            break

    wants_sort = bool(re.search(r"\b(sort|rank|order)\b", full_text, re.I)) or any(
        o.description.lower().startswith("sort_column:") for o in objectives
    )
    # Bare "top 10" / "highest" without sort still needs ordering
    wants_rank = top_n_val is not None or bool(
        re.search(r"\b(highest|lowest|largest|smallest|rank)\b", full_text, re.I)
    )

    if not wants_sort and not wants_rank:
        # Aggregate keyword with no actionable sort/groupby — leave empty
        # (caller must not silently substitute unrelated clean steps).
        return steps

    rank_col = _pick_rank_column(objectives, profile)
    if rank_col is None:
        return steps

    ascending = _parse_sort_direction(full_text)
    # Structured sort_column overrides direction token if present
    for obj in objectives:
        sm = re.match(
            r"sort_column:\s*[A-Za-z0-9_]+\s+(ascending|descending|asc|desc)\b",
            obj.description,
            re.I,
        )
        if sm:
            ascending = sm.group(1).lower() in {"ascending", "asc"}
            break

    direction = "ascending" if ascending else "descending"
    n += 1
    steps.append(Step(
        step_number=n,
        tool_name="sort_values",
        description=f"Sort rows by '{rank_col}' {direction}.",
        parameters={"column": rank_col, "ascending": ascending},
        expected_output=f"Rows ordered by '{rank_col}' {direction}.",
    ))

    # Only truncate when the user asked for top/bottom N — never for bare sort
    if top_n_val is not None:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="top_n",
            description=f"Keep top {top_n_val} rows by '{rank_col}'.",
            parameters={"n": top_n_val},
            expected_output=f"Result contains at most {top_n_val} rows.",
        ))

    return steps


def _steps_for_visualize(
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate a bar chart step if suitable columns exist."""
    steps: list[Step] = []
    n = step_offset

    numeric_cols = _numeric_columns(profile)
    id_names = {c.lower() for c in _id_columns(profile)}
    # Find a non-ID string column for X-axis labels
    label_col = next(
        (c.name for c in profile.columns
         if c.inferred_type not in {InferredType.NUMERIC, InferredType.DATE, InferredType.ID}),
        None,
    )
    value_col = next(
        (c for c in numeric_cols if c.lower() not in id_names),
        None,
    )

    if label_col and value_col:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="bar_chart",
            description=f"Generate bar chart: '{label_col}' (x) vs '{value_col}' (y).",
            parameters={"x": label_col, "y": value_col, "title": f"{value_col} by {label_col}"},
            expected_output="A PNG bar chart file is created.",
        ))

    return steps


def _steps_for_transform(
    objectives: list[Objective],
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate column/row transformation steps from structured Objective descriptions.

    Objective descriptions written by intent.py use a mini-format:
      - "drop_column: <col>"                 → drop_column tool
      - "drop_column_not_found: <name> | ..." → ToolInputError at execution
      - "add_column: <col>"                   → add_column tool
      - "rename_column: <old> to <new>"       → rename_columns tool
      - "rename_column_not_found: ..."        → ToolInputError at execution
      - "select_columns: <col>, <col>"        → select_columns tool
      - "select_columns_first: <n>"           → keep first N columns
      - Anything else: legacy regex-based filter / rename matching (fallback)
    """
    steps: list[Step] = []
    n = step_offset
    col_map = {c.name.lower(): c.name for c in profile.columns}

    for obj in objectives:
        desc = obj.description

        # ── Structured: select_columns ───────────────────────────────────────
        if desc.startswith("select_columns: "):
            raw_cols = [c.strip() for c in desc[len("select_columns: "):].split(",") if c.strip()]
            resolved: list[str] = []
            for raw in raw_cols:
                actual = col_map.get(raw.lower())
                if actual and actual not in resolved:
                    resolved.append(actual)
            if resolved:
                n += 1
                steps.append(
                    Step(
                        step_number=n,
                        tool_name="select_columns",
                        description=f"Keep only columns: {', '.join(resolved)}.",
                        parameters={"columns": resolved},
                        expected_output=f"Result contains only: {', '.join(resolved)}.",
                    )
                )
            continue

        if desc.startswith("select_columns_first: "):
            try:
                count = int(desc[len("select_columns_first: "):].strip())
            except ValueError:
                count = 0
            available = [c.name for c in (profile.columns or [])]
            resolved = available[: max(0, count)]
            if resolved:
                n += 1
                steps.append(
                    Step(
                        step_number=n,
                        tool_name="select_columns",
                        description=f"Keep first {len(resolved)} column(s): {', '.join(resolved)}.",
                        parameters={"columns": resolved},
                        expected_output=f"Result contains only: {', '.join(resolved)}.",
                    )
                )
            continue

        # ── Structured: drop_column ──────────────────────────────────────────
        if desc.startswith("drop_column: "):
            col = desc[len("drop_column: "):].strip()
            n += 1
            steps.append(
                Step(
                    step_number=n,
                    tool_name="drop_column",
                    description=f"Remove column '{col}' from the dataset.",
                    parameters={"column": col},
                    expected_output=f"Column '{col}' is absent from the result dataset.",
                )
            )
            continue

        # ── Structured: drop_column not found ────────────────────────────────
        if desc.startswith("drop_column_not_found: "):
            # Surface a plan step that will raise a ToolInputError at execution
            # time with an honest error message listing available columns.
            payload = desc[len("drop_column_not_found: "):]
            parts = payload.split(" | available: ", 1)
            requested = parts[0].strip()
            available = parts[1].strip() if len(parts) > 1 else "unknown"
            n += 1
            steps.append(
                Step(
                    step_number=n,
                    tool_name="drop_column",
                    description=(
                        f"Requested removal of column '{requested}', "
                        f"which does not exist. Available: {available}."
                    ),
                    parameters={"column": requested},
                    expected_output="This step will fail with a clear column-not-found error.",
                )
            )
            continue

        # ── Structured: add_column ───────────────────────────────────────────
        if desc.startswith("add_column: "):
            col = desc[len("add_column: "):].strip()
            n += 1
            steps.append(
                Step(
                    step_number=n,
                    tool_name="add_column",
                    description=f"Add new column '{col}' with default value None.",
                    parameters={"column": col, "default_value": None},
                    expected_output=f"Column '{col}' is present in the result dataset.",
                )
            )
            continue

        # ── Structured: rename_column ─────────────────────────────────────────
        if desc.startswith("rename_column: "):
            payload = desc[len("rename_column: "):].strip()
            parts = payload.split(" to ", 1)
            if len(parts) == 2:
                old_col, new_col = parts[0].strip(), parts[1].strip()
                n += 1
                steps.append(
                    Step(
                        step_number=n,
                        tool_name="rename_columns",
                        description=f"Rename column '{old_col}' to '{new_col}'.",
                        parameters={"mapping": {old_col: new_col}},
                        expected_output=f"Column '{new_col}' is present and '{old_col}' is absent.",
                    )
                )
            continue

        if desc.startswith("rename_column_not_found: "):
            payload = desc[len("rename_column_not_found: "):]
            parts = payload.split(" | available: ", 1)
            requested = parts[0].strip()
            available = parts[1].strip() if len(parts) > 1 else "unknown"
            n += 1
            steps.append(
                Step(
                    step_number=n,
                    tool_name="rename_columns",
                    description=(
                        f"Requested rename of column '{requested}', "
                        f"which does not exist. Available: {available}."
                    ),
                    parameters={"mapping": {requested: "__unknown__"}},
                    expected_output="This step will fail with a clear column-not-found error.",
                )
            )
            continue

        # ── Legacy fallback: row filtering and rename from raw description text ─
        # 1. Match row filtering pattern: e.g. "where Region = East"
        filter_match = re.search(
            r"\b(?:where|filter|only)\s+([A-Za-z0-9_]+)\s*(=|==|!=|>|<|>=|<=)\s*['\"]?([A-Za-z0-9_.\-]+)['\"]",
            desc,
            re.IGNORECASE,
        )
        if filter_match:
            raw_col, op, val = filter_match.groups()
            actual_col = col_map.get(raw_col.lower())
            if actual_col:
                op_norm = "==" if op == "=" else op
                target_col_info = next((c for c in profile.columns if c.name == actual_col), None)
                parsed_val: Any = val
                if target_col_info and target_col_info.inferred_type == InferredType.NUMERIC:
                    try:
                        parsed_val = float(val) if "." in val else int(val)
                    except ValueError:
                        pass
                n += 1
                steps.append(
                    Step(
                        step_number=n,
                        tool_name="filter_rows",
                        description=f"Filter rows where '{actual_col}' {op_norm} {parsed_val}.",
                        parameters={"column": actual_col, "operator": op_norm, "value": parsed_val},
                        expected_output=f"Dataset contains only rows matching '{actual_col}' {op_norm} {parsed_val}.",
                    )
                )

        # 2. Match column rename pattern: e.g. "rename CustomerID to ClientID"
        rename_match = re.search(
            r"\brename\s+([A-Za-z0-9_]+)\s+to\s+([A-Za-z0-9_]+)",
            desc,
            re.IGNORECASE,
        )
        if rename_match:
            old_col, new_col = rename_match.groups()
            actual_col = col_map.get(old_col.lower())
            if actual_col:
                n += 1
                steps.append(
                    Step(
                        step_number=n,
                        tool_name="rename_columns",
                        description=f"Rename column '{actual_col}' to '{new_col}'.",
                        parameters={"mapping": {actual_col: new_col}},
                        expected_output=f"Column '{actual_col}' is renamed to '{new_col}'.",
                    )
                )

    return steps


def _steps_for_image(
    objectives: list[Objective],
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate structural image operation steps from prompt objectives."""
    steps: list[Step] = []
    n = step_offset

    full_text = " ".join(o.description for o in objectives).lower()

    # Reject unsupported vision tasks honestly
    if any(k in full_text for k in ["describe", "description", "classify", "classification", "remove background", "background removal"]):
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="unsupported_vision_operation",
            description="Vision-based description, classification, and background removal are not supported without a vision LLM API.",
            parameters={},
            expected_output="Operation rejected as unsupported.",
        ))
        return steps

    # 1. Resize: e.g. "resize this image to 1024x1024", "resize all images to 100x100", "resize ... 1024 x 1024"
    resize_match = re.search(r"resize\b.*?\b(\d+)\s*(?:x|,|\s+)\s*(\d+)", full_text, re.I)
    if resize_match:
        w, h = int(resize_match.group(1)), int(resize_match.group(2))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="resize",
            description=f"Resize image to {w}x{h} pixels.",
            parameters={"width": w, "height": h},
            expected_output=f"Image resized to {w}x{h}.",
        ))

    # 2. Crop: e.g. "crop to 100, 100, 400, 400"
    crop_match = re.search(r"crop\s+(?:to\s+)?(\d+)[,\s]+(\d+)[,\s]+(\d+)[,\s]+(\d+)", full_text, re.I)
    if crop_match:
        l, t, r, b = int(crop_match.group(1)), int(crop_match.group(2)), int(crop_match.group(3)), int(crop_match.group(4))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="crop",
            description=f"Crop image to bounds ({l}, {t}, {r}, {b}).",
            parameters={"left": l, "top": t, "right": r, "bottom": b},
            expected_output=f"Image cropped to ({r - l}x{b - t}).",
        ))

    # 3. Rotate: e.g. "rotate 90 degrees", "rotate by 180", "rotate 270"
    rotate_match = re.search(r"rotate\s+(?:by\s+)?(\d+)", full_text, re.I)
    if rotate_match:
        deg = int(rotate_match.group(1))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="rotate",
            description=f"Rotate image by {deg} degrees.",
            parameters={"degrees": deg},
            expected_output=f"Image rotated by {deg} degrees.",
        ))

    # 4. Convert format: e.g. "convert to png", "convert to webp"
    convert_match = re.search(r"convert\s+(?:to\s+)?(png|jpg|jpeg|webp|gif|bmp|tiff|tif)", full_text, re.I)
    if convert_match:
        fmt = convert_match.group(1).lower()
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="convert_format",
            description=f"Convert image to {fmt.upper()} format.",
            parameters={"target_format": fmt},
            expected_output=f"Image converted to {fmt.upper()}.",
        ))

    # 5. Compress: e.g. "compress to 50", "compress quality 60", "compress image"
    compress_match = re.search(r"compress(?:\s+(?:image\s+)?(?:to\s+|quality\s+)?(\d+))?", full_text, re.I)
    if compress_match and "compress" in full_text:
        quality = int(compress_match.group(1)) if compress_match.group(1) else 75
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="compress",
            description=f"Compress image with quality {quality}.",
            parameters={"quality": quality},
            expected_output=f"Image compressed with quality {quality}.",
        ))

    # 6. OCR / extract text: e.g. "ocr", "extract text"
    if any(k in full_text for k in ["ocr", "extract text"]):
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_text_ocr",
            description="Extract text from image using OCR.",
            parameters={},
            expected_output="Text extracted from image via OCR.",
        ))

    # If no specific operation detected, default to metadata extraction
    if not steps:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_metadata",
            description="Extract metadata and dimensions from image.",
            parameters={},
            expected_output="Image dimensions and metadata extracted.",
        ))

    return steps


def _steps_for_audio(
    objectives: list[Objective],
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate audio operation steps from prompt objectives."""
    import re
    steps: list[Step] = []
    n = step_offset

    full_text = " ".join(o.description for o in objectives).lower()

    if any(k in full_text for k in ["trim", "cut", "slice", "clip", "crop"]):
        params: dict[str, Any] = {"start_seconds": 0.0, "end_seconds": 2.0}
        m_dur = re.search(r'(?:first|to|\b)\s*(\d+(?:\.\d+)?)\s*(?:seconds|second|sec|s\b)', full_text)
        if m_dur:
            params["end_seconds"] = float(m_dur.group(1))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="trim",
            description=f"Trim audio segment to {params.get('end_seconds', 2.0)}s.",
            parameters=params,
            expected_output="Audio segment trimmed.",
        ))
    elif any(k in full_text for k in ["convert", "format"]):
        target_fmt = "mp3"
        for fmt in ["wav", "mp3", "aac", "ogg", "flac"]:
            if fmt in full_text:
                target_fmt = fmt
                break
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="convert_format",
            description=f"Convert audio format to {target_fmt}.",
            parameters={"target_format": target_fmt},
            expected_output="Audio format converted.",
        ))
    elif any(k in full_text for k in ["compress"]):
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="compress",
            description="Compress audio.",
            parameters={"bitrate": "64k"},
            expected_output="Audio compressed.",
        ))
    else:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_metadata",
            description="Extract audio metadata (duration, sample rate, channels, bitrate).",
            parameters={},
            expected_output="Audio metadata extracted.",
        ))

    return steps


def _steps_for_video(
    objectives: list[Objective],
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate video operation steps from prompt objectives."""
    import re
    steps: list[Step] = []
    n = step_offset

    full_text = " ".join(o.description for o in objectives).lower()

    if any(k in full_text for k in ["trim", "cut", "slice", "clip"]):
        params: dict[str, Any] = {"start_seconds": 0.0, "end_seconds": 2.0}
        m_dur = re.search(r'(?:first|to|\b)\s*(\d+(?:\.\d+)?)\s*(?:seconds|second|sec|s\b)', full_text)
        if m_dur:
            params["end_seconds"] = float(m_dur.group(1))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="trim",
            description=f"Trim video segment to {params.get('end_seconds', 2.0)}s.",
            parameters=params,
            expected_output="Video segment trimmed.",
        ))
    elif any(k in full_text for k in ["frame", "snapshot", "thumbnail"]):
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_frame",
            description="Extract frame from video.",
            parameters={"timestamp_seconds": 1.0},
            expected_output="Video frame extracted.",
        ))
    elif any(k in full_text for k in ["resize", "scale", "resolution"]):
        params = {"width": 160, "height": 120}
        m_dim = re.search(r'(\d+)\s*[xX*]\s*(\d+)', full_text)
        if m_dim:
            params["width"] = int(m_dim.group(1))
            params["height"] = int(m_dim.group(2))
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="resize",
            description=f"Resize video resolution to {params['width']}x{params['height']}.",
            parameters=params,
            expected_output="Video resized.",
        ))
    elif any(k in full_text for k in ["convert", "format"]):
        target_fmt = "mp4"
        for fmt in ["webm", "mov", "avi", "mkv", "mp4"]:
            if fmt in full_text:
                target_fmt = fmt
                break
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="convert_format",
            description=f"Convert video container format to {target_fmt}.",
            parameters={"target_format": target_fmt},
            expected_output="Video format converted.",
        ))
    elif any(k in full_text for k in ["compress"]):
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="compress",
            description="Compress video file.",
            parameters={"crf": 28},
            expected_output="Video compressed.",
        ))
    elif any(k in full_text for k in ["audio", "sound", "track"]):
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_audio",
            description="Extract audio track from video.",
            parameters={"target_format": "aac"},
            expected_output="Audio track extracted from video.",
        ))
    else:
        n += 1
        steps.append(Step(
            step_number=n,
            tool_name="extract_metadata",
            description="Extract video container metadata (format, size, resolution, duration).",
            parameters={},
            expected_output="Video metadata extracted.",
        ))

    return steps


def _steps_for_archive(
    objectives: list[Objective],
    profile: DataProfile,
    step_offset: int,
) -> list[Step]:
    """Generate steps for archive processing."""
    is_list = False
    for obj in objectives:
        desc = obj.description.lower()
        if any(w in desc for w in ("list", "inspect", "contents", "show files", "manifest", "what is inside")):
            is_list = True
            break

    if is_list or not objectives:
        return [
            Step(
                step_number=step_offset + 1,
                tool_name="list_contents",
                description="List and categorize files within the archive.",
                parameters={},
                expected_output="Detailed inventory of contained files and their detected categories.",
            )
        ]

    return [
        Step(
            step_number=step_offset + 1,
            tool_name="extract_and_process",
            description="Extract archive, process matching inner files, and repackage results.",
            parameters={"objectives": [o.description for o in objectives]},
            expected_output="Repackaged archive containing processed files.",
        )
    ]


def _build_heuristic_plan(
    objectives: list[Objective],
    profile: DataProfile,
    session_id: str,
    plan_id: str,
    revision_count: int = 0,
) -> Plan:
    """Build a complete Plan from objectives using DataProfile metadata."""
    IMAGE_FORMATS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"}
    if profile.file_format in IMAGE_FORMATS:
        image_steps = _steps_for_image(objectives, profile, 0)
        dims_desc = f"{profile.width}x{profile.height}" if profile.width and profile.height else "dimensions pending"
        rationale = (
            f"Heuristic plan for image ({profile.file_format.upper()} {dims_desc}): "
            + ", ".join(s.tool_name for s in image_steps)
        )
        return Plan(
            plan_id=plan_id,
            session_id=session_id,
            objectives=objectives,
            steps=image_steps,
            rationale=rationale,
            revision_count=revision_count,
        )

    AUDIO_FORMATS = {"wav", "mp3"}
    if profile.file_format in AUDIO_FORMATS:
        audio_steps = _steps_for_audio(objectives, profile, 0)
        dur_desc = f"{profile.duration_seconds}s" if profile.duration_seconds else "duration pending"
        rationale = (
            f"Heuristic plan for audio ({profile.file_format.upper()} {dur_desc}): "
            + ", ".join(s.tool_name for s in audio_steps)
        )
        return Plan(
            plan_id=plan_id,
            session_id=session_id,
            objectives=objectives,
            steps=audio_steps,
            rationale=rationale,
            revision_count=revision_count,
        )

    VIDEO_FORMATS = {"mp4", "mov", "avi", "mkv", "webm"}
    if profile.file_format in VIDEO_FORMATS:
        video_steps = _steps_for_video(objectives, profile, 0)
        rationale = (
            f"Heuristic plan for video ({profile.file_format.upper()}): "
            + ", ".join(s.tool_name for s in video_steps)
        )
        return Plan(
            plan_id=plan_id,
            session_id=session_id,
            objectives=objectives,
            steps=video_steps,
            rationale=rationale,
            revision_count=revision_count,
        )

    ARCHIVE_FORMATS = {"zip", "tar", "gz", "tgz"}
    if profile.file_format in ARCHIVE_FORMATS:
        archive_steps = _steps_for_archive(objectives, profile, 0)
        rationale = (
            f"Heuristic plan for archive ({profile.file_format.upper()}): "
            + ", ".join(s.tool_name for s in archive_steps)
        )
        return Plan(
            plan_id=plan_id,
            session_id=session_id,
            objectives=objectives,
            steps=archive_steps,
            rationale=rationale,
            revision_count=revision_count,
        )

    all_steps: list[Step] = []
    categories = {obj.category for obj in objectives}

    if ObjectiveCategory.CLEAN in categories:
        all_steps.extend(_steps_for_clean(profile, len(all_steps)))

    if ObjectiveCategory.TRANSFORM in categories:
        trans_objs = [o for o in objectives if o.category == ObjectiveCategory.TRANSFORM]
        all_steps.extend(_steps_for_transform(trans_objs, profile, len(all_steps)))

    if ObjectiveCategory.AGGREGATE in categories:
        agg_objs = [o for o in objectives if o.category == ObjectiveCategory.AGGREGATE]
        all_steps.extend(_steps_for_aggregate(agg_objs, profile, len(all_steps)))

    if ObjectiveCategory.VISUALIZE in categories:
        all_steps.extend(_steps_for_visualize(profile, len(all_steps)))

    # Do NOT fall back to unrelated clean steps when transform/aggregate matched
    # no tools — that caused "show only 2 columns" to silently dedupe/impute instead.

    rationale = (
        f"Heuristic plan for {len(objectives)} objective(s): "
        + ", ".join(o.category.value for o in objectives)
        + f". Dataset: {profile.row_count} rows, {profile.column_count} columns."
    )

    return Plan(
        plan_id=plan_id,
        session_id=session_id,
        objectives=objectives,
        steps=all_steps,
        rationale=rationale,
        revision_count=revision_count,
    )


_ALLOWED_TOOL_NAMES = frozenset({
    # Tabular
    "drop_duplicates", "handle_missing", "fix_type_mismatches", "standardize_dates",
    "drop_column", "add_column", "select_columns", "rename_columns", "filter_rows", "add_derived_column",
    "groupby_aggregate", "sort_values", "top_n",
    "bar_chart", "line_chart", "pie_chart",
    # Document
    "extract_text", "clean_text", "count_words", "extract_headings", "extract_tables", "llm_analysis",
    # Image
    "resize", "crop", "rotate", "convert_format", "compress",
    # Audio
    "extract_metadata", "trim", "convert_format", "compress",
    # Video
    "extract_metadata", "trim", "resize", "extract_frame", "extract_audio",
    # Archive
    "list_members", "safe_extract", "process_members", "repackage",
})


def _build_llm_plan(
    objectives: list[Objective],
    profile: DataProfile,
    session_id: str,
    plan_id: str,
    llm_client: Any,
) -> Plan | None:
    """Generate an execution plan via structured LLM reasoning."""
    if not hasattr(llm_client, "generate_structured"):
        return None

    columns_summary = [
        {"name": c.name, "type": c.inferred_type.value, "null_count": c.null_count}
        for c in (profile.columns or [])
    ]
    objs_summary = [
        {"category": o.category.value, "description": o.description, "target_columns": o.target_columns, "parameters": o.parameters}
        for o in objectives
    ]

    system_prompt = (
        "You are the DataWise Deterministic Task Planner.\n"
        "Your task: Translate user objectives and data profile metadata into an ordered sequence of Steps.\n"
        "CRITICAL RULES:\n"
        "1. Strictly use ONLY tools from the registered tool catalog:\n"
        "   - drop_duplicates: params {subset: list[str]|null, keep: 'first'|'last'}\n"
        "   - handle_missing: params {strategy: 'drop'|'fill_mean'|'fill_median'|'fill_mode'|'fill_value', columns: list[str]|null, fill_value: any}\n"
        "   - fix_type_mismatches: params {column: str, target_type: 'numeric'|'date'|'string'}\n"
        "   - standardize_dates: params {column: str, target_format: '%Y-%m-%d'}\n"
        "   - drop_column: params {columns: list[str]}\n"
        "   - add_column: params {expression: str (pandas eval expr), new_column: str}\n"
        "   - rename_columns: params {mapping: {old_name: new_name}}\n"
        "   - filter_rows: params {condition: str (pandas query syntax)}\n"
        "   - groupby_aggregate: params {by: list[str], aggregations: {col: 'sum'|'mean'|'avg'|'count'|'min'|'max'}}\n"
        "   - sort_values: params {by: str|list[str], ascending: bool}\n"
        "   - top_n: params {by: str, n: int}\n"
        "   - bar_chart: params {x_column: str, y_column: str}\n"
        "   - line_chart: params {x_column: str, y_column: str}\n"
        "   - pie_chart: params {category_column: str, value_column: str}\n"
        "2. Ground all column names in the provided Available columns. Never invent non-existent column names.\n"
        "3. Step numbers must be 1-indexed integers in sequential order (1, 2, 3...).\n"
        "4. If user intent is genuinely ambiguous or contradictory, set needs_clarification=true and clarification_question.\n\n"
        "Respond with a JSON object conforming to:\n"
        "{\n"
        '  "rationale": "High-level reasoning for this plan",\n'
        '  "needs_clarification": false,\n'
        '  "clarification_question": null,\n'
        '  "steps": [\n'
        '    {\n'
        '      "step_number": 1,\n'
        '      "tool_name": "tool_name_from_catalog",\n'
        '      "description": "Explanation of what this step does",\n'
        '      "parameters": {"param": "value"},\n'
        '      "expected_output": "What state condition is expected afterwards"\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    user_content = (
        f"Objectives: {json.dumps(objs_summary)}\n\n"
        f"File format: {profile.file_format}\n"
        f"Row count: {getattr(profile, 'row_count', 'unknown')}\n"
        f"Available columns: {json.dumps(columns_summary)}"
    )

    try:
        data = llm_client.generate_structured(prompt=user_content, system_prompt=system_prompt)
        raw_steps = data.get("steps", [])
        if not raw_steps and not data.get("needs_clarification"):
            return None

        parsed_steps: list[Step] = []
        for i, stp in enumerate(raw_steps, start=1):
            if isinstance(stp, dict):
                tname = str(stp.get("tool_name", "")).strip()
                if tname not in _ALLOWED_TOOL_NAMES:
                    log.warning("LLM generated unregistered tool '%s', skipping step", tname)
                    continue
                params = stp.get("parameters") or {}
                if not isinstance(params, dict):
                    params = {}
                parsed_steps.append(
                    Step(
                        step_number=int(stp.get("step_number", i)),
                        tool_name=tname,
                        description=str(stp.get("description", f"Step {i}: {tname}")),
                        parameters=params,
                        expected_output=str(stp.get("expected_output", f"Executed {tname}")),
                    )
                )

        if parsed_steps or data.get("needs_clarification"):
            return Plan(
                plan_id=plan_id,
                session_id=session_id,
                objectives=objectives,
                steps=parsed_steps,
                needs_clarification=bool(data.get("needs_clarification", False)),
                clarification_question=data.get("clarification_question"),
                rationale=str(data.get("rationale", "LLM-synthesized deterministic execution plan.")),
                revision_count=0,
            )
    except Exception as exc:
        log.warning("LLM plan generation failed, falling back to heuristic: %s", exc)

    return None


def _build_llm_revised_plan(
    original_plan: Plan,
    validation: ValidationResult,
    profile: DataProfile,
    session_id: str,
    new_plan_id: str,
    llm_client: Any,
    revision_count: int,
) -> Plan | None:
    """Generate a revised plan via LLM diagnosing failed validation checks."""
    if not hasattr(llm_client, "generate_structured"):
        return None

    failed_info = {
        "checks_failed": validation.checks_failed,
        "details": validation.details,
    }
    prev_steps = [
        {"step_number": s.step_number, "tool_name": s.tool_name, "parameters": s.parameters, "description": s.description}
        for s in original_plan.steps
    ]

    system_prompt = (
        "You are the DataWise Plan Revision Engine.\n"
        "A previously generated execution plan failed validation checks. "
        "Review the failed validation details, diagnose why the steps failed, and produce a corrected, revised step list.\n"
        "Strictly use only registered deterministic tools.\n"
        "Return the same JSON format with 'rationale', 'needs_clarification', 'clarification_question', and 'steps'."
    )

    user_content = (
        f"Validation Failure Details: {json.dumps(failed_info)}\n\n"
        f"Previous Plan Steps: {json.dumps(prev_steps)}\n\n"
        f"Original Objectives: {json.dumps([o.description for o in original_plan.objectives])}\n"
        f"Columns: {json.dumps([c.name for c in (profile.columns or [])])}"
    )

    try:
        data = llm_client.generate_structured(prompt=user_content, system_prompt=system_prompt)
        raw_steps = data.get("steps", [])
        if not raw_steps:
            return None

        parsed_steps: list[Step] = []
        for i, stp in enumerate(raw_steps, start=1):
            if isinstance(stp, dict):
                tname = str(stp.get("tool_name", "")).strip()
                if tname not in _ALLOWED_TOOL_NAMES:
                    continue
                params = stp.get("parameters") or {}
                if not isinstance(params, dict):
                    params = {}
                parsed_steps.append(
                    Step(
                        step_number=int(stp.get("step_number", i)),
                        tool_name=tname,
                        description=str(stp.get("description", f"Step {i}: {tname}")),
                        parameters=params,
                        expected_output=str(stp.get("expected_output", f"Executed {tname}")),
                    )
                )

        if parsed_steps:
            return Plan(
                plan_id=new_plan_id,
                session_id=session_id,
                objectives=original_plan.objectives,
                steps=parsed_steps,
                needs_clarification=bool(data.get("needs_clarification", False)),
                clarification_question=data.get("clarification_question"),
                rationale=str(data.get("rationale", f"Revised plan after validation failure: {', '.join(validation.checks_failed)}")),
                revision_count=revision_count,
            )
    except Exception as exc:
        log.warning("LLM plan revision failed, falling back to heuristic: %s", exc)

    return None


def create_plan(
    objectives: list[Objective],
    profile: DataProfile,
    session_id: str,
    llm_client: object | None = None,
    llm_call_counter: Any = None,
) -> Plan:
    """Convert a list of Objectives into an executable Plan.

    Args:
        objectives: Parsed objectives from Stage 2 intent understanding.
        profile: Metadata DataProfile from Stage 1. Contains column types,
                 null counts, and duplicate counts used for grounded planning.
        session_id: Session this plan belongs to.
        llm_client: Optional LLM client for Phase 4+ structured-output planning.
        llm_call_counter: Optional counter callback for budget tracking.

    Returns:
        A validated, inspectable Plan with steps mapping 1:1 to tool functions.
    """
    plan_id = str(uuid.uuid4())

    if llm_client is not None and llm_call_counter is not None:
        llm_call_counter("build_plan")

    # LLM-backed structured planning path
    if llm_client is not None:
        llm_plan = _build_llm_plan(objectives, profile, session_id, plan_id, llm_client)
        if llm_plan is not None:
            return llm_plan

    return _build_heuristic_plan(objectives, profile, session_id, plan_id)


# Alias for create_plan per architecture spec
build_plan = create_plan


def revise_plan(
    original_plan: Plan,
    validation: ValidationResult,
    profile: DataProfile,
    llm_client: object | None = None,
    llm_call_counter: Any = None,
) -> Plan:
    """Produce a revised Plan after a validation failure.

    Called exclusively by pipeline.py's bounded retry loop.
    NEVER called from executor.py or validator.py.

    Args:
        original_plan: The plan that failed validation.
        validation: The ValidationResult explaining what went wrong.
        profile: The original DataProfile (schema hasn't changed).
        llm_client: Optional LLM client for smarter revision in Phase 4+.
        llm_call_counter: Optional counter callback for budget tracking.

    Returns:
        A revised Plan with revision_count incremented.
    """
    new_plan_id = str(uuid.uuid4())

    if llm_client is not None and llm_call_counter is not None:
        llm_call_counter("revise_plan")

    # LLM-driven revision path
    if llm_client is not None:
        revised = _build_llm_revised_plan(
            original_plan,
            validation,
            profile,
            original_plan.session_id,
            new_plan_id,
            llm_client,
            revision_count=original_plan.revision_count + 1,
        )
        if revised is not None:
            return revised

    return _build_heuristic_plan(
        original_plan.objectives,
        profile,
        original_plan.session_id,
        new_plan_id,
        revision_count=original_plan.revision_count + 1,
    )


def check_ambiguity_and_clarification(
    objectives: list[Objective],
    profile: DataProfile,
    session_id: str,
    prompt: str = "",
) -> ClarificationRequest | None:
    """Detect genuine ambiguity in user intent and return a ClarificationRequest if found.

    Returns None if the intent is clear enough to proceed with sensible defaults.

    Args:
        objectives: Parsed objectives.
        profile: DataProfile of the dataset.
        session_id: Current session identifier.
        prompt: Raw natural-language prompt from the user.

    Returns:
        ClarificationRequest if ambiguous, else None.
    """
    p_lower = prompt.lower().strip()

    # 1. Underspecified filter request (e.g. "filter data" without condition or column)
    if re.search(r"^\s*(filter|remove|drop)\s+(the\s+)?(data|rows?)\s*$", p_lower):
        return ClarificationRequest(
            session_id=session_id,
            question="Which rows or condition should be filtered?",
            context="The prompt requested filtering rows but did not specify which condition or column to filter on.",
            options=["Filter null values", "Filter specific values", "Keep all rows"],
            default_choice="Keep all rows",
        )

    # 2. Underspecified calculation (e.g. "calculate" without operation or formula)
    if re.search(r"^\s*(calculate|compute)\s*(a\s+new\s+column)?\s*$", p_lower):
        return ClarificationRequest(
            session_id=session_id,
            question="What calculation would you like to perform?",
            context="The prompt requested a calculation without specifying the formula or column.",
            options=["Sum of numeric columns", "Average of numeric columns", "Row count"],
            default_choice="Row count",
        )

    # 3. Check if any objective explicitly flags ambiguity
    for obj in objectives:
        if getattr(obj, "needs_clarification", False):
            return ClarificationRequest(
                session_id=session_id,
                question=f"Please clarify the operation for {obj.category.value}.",
                context=obj.description,
            )

    return None
