"""DataWise Archive Processor.

Implements the FileProcessor interface for ZIP, TAR, and GZ archives.
Provides profiling with magic-byte content detection, safe listing,
and extract-and-process workflows delegating to specialized format processors.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Any, Tuple
import uuid
import zipfile
import tarfile

from backend.core.archive_security import (
    SafeArchiveWorkspace,
    create_safe_archive,
    safe_extract_archive,
    validate_archive_security,
)
from backend.core.exceptions import ExecutionError, FileValidationError
from backend.core.file_detection import FileCategory, detect_file
from backend.models.schemas import (
    ColumnInfo,
    ExecutionResult,
    InferredType,
    Objective,
    Plan,
    Step,
    ValidationResult,
)
from backend.processors.base import FileProcessor

log = logging.getLogger(__name__)


class ArchiveProcessor(FileProcessor):
    """Processor for archive containers (ZIP, TAR, GZ)."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}

    def cleanup(self, session_id: str) -> None:
        """Clean up cached session data."""
        keys_to_delete = [k for k in self._cache.keys() if session_id in str(k)]
        for k in keys_to_delete:
            del self._cache[k]

    def profile(self, file_path: Path, session_id: str = "") -> dict[str, Any]:
        """Profile archive structure and detect member content types using magic bytes."""
        if not file_path.exists():
            raise FileValidationError(f"Archive not found: {file_path}")

        # 1. Pre-extraction security check
        manifest = validate_archive_security(file_path)

        ext = file_path.suffix.lower().lstrip(".")
        if file_path.name.lower().endswith(".tar.gz") or file_path.name.lower().endswith(".tgz"):
            ext = "tar.gz"

        session_dir = file_path.parent
        entries_detail: list[dict[str, Any]] = []
        categories_found: set[str] = set()

        # 2. Extract into safe isolated workspace to perform magic-byte content detection
        with SafeArchiveWorkspace(session_dir, prefix="profile_arc_") as tmp_dir:
            extracted = safe_extract_archive(file_path, tmp_dir, session_id=session_id)
            for item in extracted:
                detection = detect_file(item)
                cat_str = detection.detected_category.value
                categories_found.add(cat_str)
                entries_detail.append({
                    "filename": item.name,
                    "rel_path": str(item.relative_to(tmp_dir)).replace("\\", "/"),
                    "size_bytes": item.stat().st_size,
                    "category": cat_str,
                    "format": detection.extension.lstrip("."),
                    "mime_type": detection.mime_type,
                })

        entry_count = len(entries_detail)
        total_size = sum(e["size_bytes"] for e in entries_detail)

        # Build column profile for tabular/frontend compatibility
        col_names = ["Filename", "Category", "Format", "Size"]
        col_types = {
            "Filename": "text",
            "Category": "categorical",
            "Format": "categorical",
            "Size": "numeric",
        }
        columns_info = [
            ColumnInfo(
                name="Filename",
                inferred_type=InferredType.TEXT,
                raw_dtype="string",
                null_count=0,
                null_percentage=0.0,
                unique_count=entry_count,
            ),
            ColumnInfo(
                name="Category",
                inferred_type=InferredType.CATEGORICAL,
                raw_dtype="category",
                null_count=0,
                null_percentage=0.0,
                unique_count=len(categories_found),
            ),
            ColumnInfo(
                name="Format",
                inferred_type=InferredType.CATEGORICAL,
                raw_dtype="category",
                null_count=0,
                null_percentage=0.0,
                unique_count=len({e["format"] for e in entries_detail}),
            ),
            ColumnInfo(
                name="Size",
                inferred_type=InferredType.NUMERIC,
                raw_dtype="int64",
                null_count=0,
                null_percentage=0.0,
                unique_count=len({e["size_bytes"] for e in entries_detail}),
            ),
        ]

        summary = (
            f"Archive ({ext.upper()}) containing {entry_count} file(s) "
            f"({total_size / (1024 * 1024):.2f} MB uncompressed) across categories: "
            f"{', '.join(sorted(categories_found))}."
        )

        return {
            "file_format": ext,
            "row_count": entry_count,
            "column_count": 4,
            "column_names": col_names,
            "column_types": col_types,
            "columns": [c.model_dump() for c in columns_info],
            "missing_values": {},
            "unique_counts": {},
            "duplicate_rows": 0,
            "memory_usage_bytes": total_size,
            "file_size": file_path.stat().st_size,
            "entry_count": entry_count,
            "total_uncompressed_bytes": total_size,
            "contained_categories": sorted(list(categories_found)),
            "entries": entries_detail,
            "summary": summary,
        }

    def validate_input(self, file_path: Path, operation: Objective) -> Tuple[bool, str]:
        """Validate whether the requested objective can be applied to this archive."""
        if not file_path.exists():
            return False, f"File does not exist: {file_path}"
        return True, ""

    def execute(self, file_path: Path, structured_operation: Any, **kwargs) -> dict[str, Any]:
        """Execute archive operation: list_contents or extract_and_process."""
        output_dir = kwargs.get("output_dir", file_path.parent)
        session_id = kwargs.get("session_id", str(uuid.uuid4()))

        # Determine if this is a listing or an extract_and_process request
        is_list_only = False
        inner_plan: Plan | None = None

        if isinstance(structured_operation, Plan):
            inner_plan = structured_operation
            step_names = [s.tool_name.lower() for s in structured_operation.steps]
            if "list_contents" in step_names and len(step_names) == 1:
                is_list_only = True
        elif isinstance(structured_operation, str):
            if structured_operation.lower() in ("list", "list_contents", "profile"):
                is_list_only = True

        ext = file_path.suffix.lower().lstrip(".")
        if file_path.name.lower().endswith(".tar.gz") or file_path.name.lower().endswith(".tgz"):
            ext = "tar.gz"

        working_extract_dir = output_dir / f"work_arc_{uuid.uuid4().hex[:6]}"
        try:
            extracted_files = safe_extract_archive(file_path, working_extract_dir, session_id=session_id)

            from backend.processors.registry import get_processor

            processed_items: list[dict[str, Any]] = []
            files_to_repackage: list[tuple[Path, str]] = []
            step_results: list[ExecutionResult] = []

            for member_path in extracted_files:
                rel_name = str(member_path.relative_to(working_extract_dir)).replace("\\", "/")
                detection = detect_file(member_path)
                member_cat = detection.detected_category

                if is_list_only:
                    files_to_repackage.append((member_path, rel_name))
                    processed_items.append({
                        "filename": rel_name,
                        "category": member_cat.value,
                        "action": "listed",
                        "size": member_path.stat().st_size,
                    })
                    continue

                # extract_and_process: attempt to process member if relevant
                processed = False
                try:
                    target_processor = get_processor(member_cat)
                    # Check if the inner plan has steps applicable to this category
                    applicable = False
                    if inner_plan and inner_plan.steps:
                        for st in inner_plan.steps:
                            # Match category by tool name heuristics
                            t_name = st.tool_name.lower()
                            if member_cat == FileCategory.IMAGE and any(k in t_name for k in ("image", "resize", "crop", "rotate")):
                                applicable = True
                            elif member_cat == FileCategory.TABULAR and any(k in t_name for k in ("clean", "transform", "filter", "drop", "add")):
                                applicable = True
                            elif member_cat == FileCategory.DOCUMENT and any(k in t_name for k in ("extract", "text", "document")):
                                applicable = True

                    if applicable:
                        member_out_dir = working_extract_dir / "proc"
                        member_out_dir.mkdir(exist_ok=True)
                        res_state = target_processor.execute(member_path, inner_plan, output_dir=member_out_dir)
                        # Export processed file
                        exported = target_processor.export(
                            res_state,
                            output_format=detection.extension.lstrip("."),
                            output_dir=member_out_dir,
                            filename_stem=member_path.stem + "_processed",
                        )
                        files_to_repackage.append((exported, rel_name))
                        processed_items.append({
                            "filename": rel_name,
                            "category": member_cat.value,
                            "action": "processed",
                            "original_size": member_path.stat().st_size,
                            "new_size": exported.stat().st_size,
                        })
                        processed = True
                except Exception as exc:
                    log.warning("Could not process member '%s': %s", rel_name, exc)

                if not processed:
                    # Keep original file in archive untouched
                    files_to_repackage.append((member_path, rel_name))
                    processed_items.append({
                        "filename": rel_name,
                        "category": member_cat.value,
                        "action": "preserved",
                        "size": member_path.stat().st_size,
                    })

            # Re-package into destination archive
            out_archive_ext = "zip" if ext in ("zip", "") else ext
            result_archive_path = output_dir / f"result.{out_archive_ext}"
            create_safe_archive(files_to_repackage, result_archive_path, archive_format=out_archive_ext)

            # Record step result
            step_results.append(
                ExecutionResult(
                    step_number=1,
                    tool_name="list_contents" if is_list_only else "extract_and_process",
                    success=True,
                    rows_before=len(files_to_repackage),
                    rows_after=len(files_to_repackage),
                    columns_before=4,
                    columns_after=4,
                    summary=f"Archive processed: {len(files_to_repackage)} files packaged into {result_archive_path.name}.",
                    execution_time_ms=0.0,
                )
            )

            # Table preview for frontend display
            preview_rows = [
                {
                    "Filename": p["filename"],
                    "Category": p["category"],
                    "Action": p["action"],
                    "Size": f"{p.get('new_size', p.get('size', 0)):,} B",
                }
                for p in processed_items
            ]

            return {
                "result_archive_path": result_archive_path,
                "total_files": len(files_to_repackage),
                "processed_count": sum(1 for p in processed_items if p["action"] == "processed"),
                "processed_items": processed_items,
                "step_results": step_results,
                "chart_paths": [],
                "preview_rows": preview_rows,
                "preview_columns": ["Filename", "Category", "Action", "Size"],
            }

        finally:
            if working_extract_dir.exists():
                shutil.rmtree(working_extract_dir, ignore_errors=True)

    def validate_output(
        self,
        before_state: Any,
        after_state: Any,
        structured_operation: Any,
        **kwargs,
    ) -> ValidationResult:
        """Validate output archive existence, safety, and member count."""
        retry_count = kwargs.get("retry_count", 0)
        max_retries = kwargs.get("max_retries", 2)

        if not isinstance(after_state, dict) or "result_archive_path" not in after_state:
            return ValidationResult(
                is_valid=False,
                checks_passed=[],
                checks_failed=["MISSING_OUTPUT_ARCHIVE"],
                details={"MISSING_OUTPUT_ARCHIVE": "Execution did not produce an output archive."},
                can_retry=False,
                retry_count=retry_count,
                max_retries=max_retries,
            )

        archive_path: Path = Path(after_state["result_archive_path"])

        # Check 1: File exists and has non-zero size
        if not archive_path.exists() or archive_path.stat().st_size == 0:
            return ValidationResult(
                is_valid=False,
                checks_passed=[],
                checks_failed=["EMPTY_OUTPUT_ARCHIVE"],
                details={"EMPTY_OUTPUT_ARCHIVE": "Exported archive file is missing or empty."},
                can_retry=False,
                retry_count=retry_count,
                max_retries=max_retries,
            )

        # Check 2: Opens and passes security validation
        try:
            manifest = validate_archive_security(archive_path)
        except Exception as exc:
            return ValidationResult(
                is_valid=False,
                checks_passed=["FILE_EXISTS"],
                checks_failed=["ARCHIVE_CORRUPTED_OR_INSECURE"],
                details={"ARCHIVE_CORRUPTED_OR_INSECURE": str(exc)},
                can_retry=False,
                retry_count=retry_count,
                max_retries=max_retries,
            )

        # Check 3: Expected entry count
        expected_count = after_state.get("total_files", 0)
        if manifest.entry_count != expected_count:
            return ValidationResult(
                is_valid=False,
                checks_passed=["FILE_EXISTS", "SECURITY_VERIFIED"],
                checks_failed=["ENTRY_COUNT_MISMATCH"],
                details={
                    "ENTRY_COUNT_MISMATCH": (
                        f"Expected {expected_count} entries, found {manifest.entry_count}."
                    )
                },
                can_retry=True,
                retry_count=retry_count,
                max_retries=max_retries,
            )

        return ValidationResult(
            is_valid=True,
            checks_passed=["FILE_EXISTS", "SECURITY_VERIFIED", "ENTRY_COUNT_MATCHED"],
            checks_failed=[],
            details={
                "FILE_EXISTS": f"Archive {archive_path.name} created ({archive_path.stat().st_size} bytes).",
                "SECURITY_VERIFIED": "No path traversal or bomb patterns found in output archive.",
                "ENTRY_COUNT_MATCHED": f"Contained {manifest.entry_count} verified entries.",
            },
            can_retry=False,
            retry_count=retry_count,
            max_retries=max_retries,
        )

    def export(self, state: Any, output_format: str, output_dir: Path, **kwargs) -> Path:
        """Export archive to requested output location."""
        current_path: Path = Path(state["result_archive_path"])
        filename_stem = kwargs.get("filename_stem", "result")
        target_ext = output_format.lower().lstrip(".")
        if target_ext not in ("zip", "tar", "gz", "tar.gz"):
            target_ext = current_path.suffix.lstrip(".") or "zip"

        output_dir.mkdir(parents=True, exist_ok=True)
        target_path = output_dir / f"{filename_stem}.{target_ext}"
        if current_path == target_path:
            return target_path

        shutil.copy2(current_path, target_path)
        return target_path
