"""DataWise Pipeline Orchestrator.

Wires Stages 1–6 into a single, fully-supervised execution:
  Stage 1  InputManager.validate_and_save()   → file storage, session_id
  Stage 1b DataUnderstanding.profile_data()   → DataProfile
  Stage 2  IntentUnderstanding.parse_intent() → list[Objective]
  Stage 3  TaskPlanner.build_plan()           → Plan (with clarification check)
  Stage 4  ExecutionLayer.execute_plan()      → (DataFrame, list[ExecutionResult], chart_paths)
  Stage 5  ValidationLayer.validate()         → ValidationResult
  Stage 6  OutputGenerator                   → PipelineOutput

ARCHITECTURE CONTRACT [FIX F2 + FIX F9]:
  - THIS MODULE OWNS THE ONLY RETRY LOOP IN THE SYSTEM.
    An explicit bounded `for attempt in range(MAX_RETRIES + 1)` loop.
    Hard-capped at 3 total attempts (1 initial + 2 retries).
    No recursion (recursion risks stack depth issues and is harder to reason about).
    executor.py and validator.py are stateless — they do ONE thing each.
  - THIS MODULE OWNS THE ONLY LLM-CALL BUDGET ENFORCEMENT.
    MAX_LLM_CALLS_PER_REQUEST caps the total number of LLM calls (intent + plan +
    revisions) per request. Exceeded budget → raises LLMBudgetExceededError.
  - All exceptions from tool/executor/validator layers are caught here and
    mapped to sanitized PipelineOutput with plain-English error messages.
    No raw stack traces are ever exposed to the caller.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, BinaryIO

from fastapi import UploadFile
import pandas as pd

from backend.config import SESSIONS_DIR
from backend.core.exceptions import (
    DataWiseError,
    DataWiseValidationError,
    ExecutionError,
    FileValidationError,
    LLMBudgetExceededError,
    ToolInputError,
)
from backend.core.executor import ExecutorError, execute_plan
from backend.core.input_manager import InputManager
from backend.core.intent import parse_intent
from backend.core.output import (
    export_result_file,
    format_table_preview,
    synthesize_plain_english_summary,
)
from backend.core.planner import (
    build_plan,
    check_ambiguity_and_clarification,
    create_plan,
    revise_plan,
)
import shutil
import uuid

from backend.core.archive_security import create_safe_archive
from backend.core.file_detection import FileCategory, detect_file
from backend.core.understanding import DataUnderstanding
from backend.core.validator import validate
from backend.models.schemas import (
    BatchItemResult,
    BatchSummary,
    DataProfile,
    ExecutionResult,
    Plan,
    PipelineOutput,
    PipelineStatus,
    ValidationResult,
)
from backend.processors.registry import get_processor

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline constants
# ---------------------------------------------------------------------------

# Maximum number of plan-execute-validate retry attempts AFTER the first try.
# Total attempts = 1 (initial) + MAX_RETRIES = 3 total attempts maximum.
MAX_RETRIES: int = 2

# Maximum LLM API calls permitted per pipeline request [FIX F9].
MAX_LLM_CALLS_PER_REQUEST: int = 6

# Preview row limit for the result table
_PREVIEW_MAX_ROWS: int = 50

# Default export format
_DEFAULT_EXPORT_FORMAT: str = "csv"


def infer_export_format_from_prompt(prompt: str, current: str = _DEFAULT_EXPORT_FORMAT) -> str:
    """Override export format when the user asks to convert/save as csv|xlsx|json."""
    text = (prompt or "").strip()
    m = re.search(
        r"\b(?:convert|export|save|download|output|change|write)\b"
        r".*?\b(?:to|as|into)\s+(csv|xlsx|excel|json)\b"
        r"|\b(?:to|as|into)\s+(csv|xlsx|excel|json)\b",
        text,
        re.I,
    )
    if not m:
        # Also honour structured convert objectives later via parameters
        return current
    raw = next(g for g in m.groups() if g).lower()
    return "xlsx" if raw == "excel" else raw


def resolve_export_format(prompt: str, objectives: list, current: str) -> str:
    """Prefer explicit convert objective params, then prompt inference, then UI default."""
    for obj in objectives or []:
        params = getattr(obj, "parameters", None) or {}
        fmt = params.get("export_format")
        if isinstance(fmt, str) and fmt.lower() in {"csv", "xlsx", "json"}:
            return fmt.lower()
        desc = getattr(obj, "description", "") or ""
        if desc.startswith("convert_to: "):
            fmt2 = desc.split(":", 1)[1].strip().lower()
            if fmt2 == "excel":
                fmt2 = "xlsx"
            if fmt2 in {"csv", "xlsx", "json"}:
                return fmt2
    return infer_export_format_from_prompt(prompt, current)


class LLMCallCounter:
    """Per-request counter tracking LLM API invocations against a hard budget cap."""

    def __init__(self, max_calls: int = MAX_LLM_CALLS_PER_REQUEST) -> None:
        self.max_calls = max_calls
        self.call_count = 0

    def increment(self, stage_name: str = "") -> int:
        self.call_count += 1
        if self.call_count > self.max_calls:
            raise LLMBudgetExceededError(
                f"LLM call budget of {self.max_calls} calls per request exceeded "
                f"(attempted call #{self.call_count} at stage: '{stage_name}')."
            )
        return self.call_count

    def __call__(self, stage_name: str = "") -> int:
        return self.increment(stage_name)


class DataWisePipeline:
    """Orchestrates the end-to-end DataWise pipeline for a single request.

    Usage::

        pipeline = DataWisePipeline()
        output = pipeline.run(file_bytes, filename, prompt)

    Attributes:
        llm_client: Optional LLM provider client. When None, fully deterministic
                    heuristic planning is used (no API calls, suitable for CI/testing).
        sessions_dir: Optional override for the session storage root directory.
        max_llm_calls: Hard limit on LLM API calls for this pipeline instance.
    """

    def __init__(
        self,
        llm_client: object | None = None,
        sessions_dir: Path | None = None,
        max_llm_calls: int = MAX_LLM_CALLS_PER_REQUEST,
    ) -> None:
        self.llm_client = llm_client
        self.sessions_dir = sessions_dir or SESSIONS_DIR
        self.max_llm_calls = max_llm_calls
        self.last_attempt_count: int = 0

    # ------------------------------------------------------------------
    # Error helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _error_output(
        session_id: str,
        message: str,
        plan: Plan | None = None,
        step_results: list[ExecutionResult] | None = None,
        validation: ValidationResult | None = None,
    ) -> PipelineOutput:
        """Construct a standardized failed PipelineOutput with plain-English explanation."""
        return PipelineOutput(
            session_id=session_id,
            status=PipelineStatus.FAILED,
            summary=message,
            preview_rows=[],
            preview_columns=[],
            total_rows=0,
            chart_paths=[],
            executed_plan=plan,
            validation=validation,
            errors=[message],
        )

    # ------------------------------------------------------------------
    # Main execution entry point
    # ------------------------------------------------------------------

    def run(
        self,
        uploaded_file: bytes | BinaryIO | Path | UploadFile,
        original_filename: str,
        prompt: str,
        session_id: str | None = None,
        export_format: str = _DEFAULT_EXPORT_FORMAT,
        raise_on_error: bool = False,
    ) -> PipelineOutput:
        """Execute the end-to-end DataWise pipeline on an uploaded file.

        Args:
            uploaded_file: File bytes, open stream, Path, or FastAPI UploadFile.
            original_filename: Original client filename (for extension check).
            prompt: User's natural-language instruction.
            session_id: Optional UUID session ID override. Generated if omitted.
            export_format: Output file format — 'csv', 'xlsx', or 'json'.
            raise_on_error: If True, re-raises domain exceptions instead of wrapping
                            in PipelineOutput(status=FAILED). Useful for HTTP 4xx/5xx mapping.

        Returns:
            PipelineOutput with status, summary, preview, file path, and charts.
        """
        # Per-request LLM budget counter [FIX F9]
        llm_call_counter = LLMCallCounter(max_calls=self.max_llm_calls)

        sid = session_id or ""  # filled in after Stage 1

        # ==============================================================
        # Stage 1a — Input validation and secure storage
        # ==============================================================
        try:
            sid, internal_path = InputManager.validate_and_save(
                uploaded_file,
                original_filename=original_filename,
                session_id=session_id or None,
                sessions_dir=self.sessions_dir,
            )
        except FileValidationError as exc:
            log.warning("Stage 1 (input): %s", exc.message)
            if raise_on_error:
                raise
            return self._error_output(sid, f"File rejected: {exc.message}")
        except Exception:
            log.exception("Stage 1 (input) unexpected error")
            if raise_on_error:
                raise
            return self._error_output(sid, "An unexpected error occurred during file upload.")

        session_dir = internal_path.parent

        # ==============================================================
        # NEW: Stage 1.5 — File Detection and Processor Routing
        # ==============================================================
        from backend.core.file_detection import detect_file
        from backend.processors.registry import get_processor, UnsupportedFileTypeError
        
        detection = detect_file(internal_path, original_filename)
        try:
            processor = get_processor(detection.detected_category)
        except UnsupportedFileTypeError:
            err_msg = f"Unsupported file category: '{detection.detected_category.value}'. Currently only 'tabular' is supported."
            log.warning("Stage 1.5 (detection): %s", err_msg)
            if raise_on_error:
                raise FileValidationError(err_msg)
            return self._error_output(sid, err_msg)

        # ==============================================================
        # Stage 1b — Data understanding and profiling (via processor)
        # ==============================================================
        try:
            profile_dict = processor.profile(internal_path, session_id=sid)
            # Rehydrate the Pydantic schema for the intent/planning layers
            from backend.models.schemas import DataProfile
            profile = DataProfile(**profile_dict)
        except (FileValidationError, DataWiseError) as exc:
            log.warning("Stage 1b (profiling): %s", exc.message)
            if raise_on_error:
                raise
            return self._error_output(sid, f"Could not profile the uploaded file: {exc.message}")
        except Exception:
            log.exception("Stage 1b (profiling) unexpected error")
            if raise_on_error:
                raise
            return self._error_output(sid, "An unexpected error occurred while profiling the data.")

        # ==============================================================
        # Stage 2 — Intent understanding
        # ==============================================================
        try:
            objectives = parse_intent(
                prompt,
                profile,
                llm_client=self.llm_client,
                llm_call_counter=llm_call_counter,
            )
        except LLMBudgetExceededError as exc:
            if raise_on_error:
                raise
            return self._error_output(sid, str(exc))
        except Exception:
            log.exception("Stage 2 (intent) unexpected error")
            if raise_on_error:
                raise
            return self._error_output(sid, "Could not understand the instruction provided.")

        # Honour "convert to json/csv/xlsx" in the prompt even if the UI dropdown differs
        export_format = resolve_export_format(prompt, objectives, export_format)

        # ==============================================================
        # Stage 3 (initial) — Task planning
        # ==============================================================
        try:
            plan = build_plan(
                objectives,
                profile,
                session_id=sid,
                llm_client=self.llm_client,
                llm_call_counter=llm_call_counter,
            )
        except LLMBudgetExceededError as exc:
            if raise_on_error:
                raise
            return self._error_output(sid, str(exc))
        except Exception:
            log.exception("Stage 3 (planning) unexpected error")
            if raise_on_error:
                raise
            return self._error_output(sid, "Could not create an execution plan for the instruction.")

        # Check for ambiguity / clarification short-circuit before execution
        clarification = check_ambiguity_and_clarification(
            objectives, profile, sid, prompt=prompt
        )
        if clarification is not None:
            log.info("Stage 3 short-circuit: clarification required for session %s", sid)
            return PipelineOutput(
                session_id=sid,
                status=PipelineStatus.NEEDS_CLARIFICATION,
                summary=clarification.question,
                total_rows=getattr(profile, "row_count", 0),
                executed_plan=plan,
                errors=[clarification.question],
            )
        if plan.needs_clarification:
            q = plan.clarification_question or "Clarification is needed before proceeding."
            return PipelineOutput(
                session_id=sid,
                status=PipelineStatus.NEEDS_CLARIFICATION,
                summary=q,
                total_rows=getattr(profile, "row_count", 0),
                executed_plan=plan,
                errors=[q],
            )

        # ==============================================================
        # Stages 4 + 5 — Bounded execute → validate retry loop [FIX F2]
        # ==============================================================
        # This is the ONLY retry loop in the system.
        # An explicit for-loop (not recursion) for clarity and stack-safety.
        # Hard cap: range(MAX_RETRIES + 1) = 3 total attempts maximum.

        after_state: Any = None
        all_step_results: list[ExecutionResult] = []
        chart_paths: list[str] = []
        validation: ValidationResult | None = None
        last_error: str | None = None
        self.last_attempt_count = 0

        for attempt in range(MAX_RETRIES + 1):
            self.last_attempt_count = attempt + 1
            if attempt > 0:
                # Revision: produce a new plan based on the validation failure
                log.info(
                    "Pipeline retry attempt %d/%d for session %s",
                    attempt,
                    MAX_RETRIES,
                    sid,
                )
                try:
                    plan = revise_plan(
                        plan,
                        validation,
                        profile,
                        llm_client=self.llm_client,
                        llm_call_counter=llm_call_counter,
                    )
                except LLMBudgetExceededError as exc:
                    last_error = str(exc)
                    if raise_on_error:
                        raise
                    break
                except Exception:
                    log.exception("Stage 3 (plan revision) unexpected error")
                    last_error = "Could not revise the plan after a validation failure."
                    break

            # Stage 4 — Execute via processor
            try:
                after_state = processor.execute(internal_path, plan, output_dir=session_dir)
                # For summary and preview later, we rely on processor-specific state.
                # Since TabularProcessor returns a dict with 'final_df', we'll extract for those.
                all_step_results = after_state.get("step_results", [])
                chart_paths = after_state.get("chart_paths", [])

            except (ExecutorError, ExecutionError, ToolInputError, DataWiseError, ValueError) as exc:
                last_error = f"Execution failed: {exc.message if hasattr(exc, 'message') else str(exc)}"
                log.warning("Stage 4 (execution) attempt %d: %s", attempt, last_error)
                # No point validating a completely failed execution — retry immediately if attempts remain
                if attempt < MAX_RETRIES:
                    validation = ValidationResult(
                        is_valid=False,
                        checks_failed=["EXECUTION_ERROR"],
                        details={"EXECUTION_ERROR": last_error},
                        can_retry=True,
                        retry_count=attempt,
                        max_retries=MAX_RETRIES,
                    )
                    continue
                if raise_on_error:
                    raise
                break
            except Exception:
                log.exception("Stage 4 (execution) unexpected error attempt %d", attempt)
                last_error = "An unexpected error occurred during execution."
                if raise_on_error:
                    raise
                break

            # Stage 5 — Validate via processor
            validation = processor.validate_output(
                before_state=internal_path,
                after_state=after_state,
                structured_operation=plan,
                retry_count=attempt,
                max_retries=MAX_RETRIES,
            )

            if validation.is_valid:
                last_error = None
                break  # Success — exit the retry loop

            # Validation failed; decide whether to retry
            log.info(
                "Validation failed (attempt %d): checks_failed=%s",
                attempt,
                validation.checks_failed,
            )
            if not validation.can_retry or attempt >= MAX_RETRIES:
                last_error = (
                    f"Validation failed after {attempt + 1} attempt(s): "
                    + ", ".join(validation.checks_failed)
                )
                break

        # ==============================================================
        # Stage 6 — Output generation
        # ==============================================================

        # Export processed file via processor
        result_file_path: str | None = None
        result_filename: str | None = None
        try:
            if after_state is not None:
                result_path = processor.export(
                    state=after_state,
                    output_format=export_format,
                    output_dir=session_dir,
                    filename_stem="result"
                )
                result_file_path = str(result_path)
                result_filename = result_path.name
        except Exception:
            log.exception("Stage 6 (export) failed")
            # Non-fatal — pipeline output still includes preview and summary

        # Table preview (tabular-specific, falling back gracefully for non-tabular)
        preview_rows = []
        preview_columns = []
        total_rows = 0
        if after_state and "final_df" in after_state:
            final_df = after_state["final_df"]
            preview_rows, preview_columns = format_table_preview(final_df, max_rows=_PREVIEW_MAX_ROWS)
            total_rows = len(final_df)
        elif after_state and "preview_rows" in after_state:
            preview_rows = after_state["preview_rows"]
            preview_columns = after_state.get("preview_columns", [])
            total_rows = len(preview_rows)
        elif profile:
            total_rows = getattr(profile, "row_count", 0)


        # Plain-English summary built from execution telemetry
        summary = synthesize_plain_english_summary(plan, all_step_results, validation)
        convert_fmt = resolve_export_format(prompt, objectives, "")
        if convert_fmt in {"csv", "xlsx", "json"} and (
            not all_step_results or summary.startswith("No steps")
        ):
            summary = (
                f"Converted tabular data to {convert_fmt.upper()} for download "
                f"(file: {result_filename or f'result.{convert_fmt}'})."
            )
        elif convert_fmt in {"csv", "xlsx", "json"} and any(
            (getattr(o, "description", "") or "").startswith("convert_to:")
            for o in objectives
        ):
            summary = f"Exported as {convert_fmt.upper()}. " + summary

        # Determine overall status
        if last_error:
            status = PipelineStatus.FAILED
            errors = [last_error]
        elif validation is not None and not validation.is_valid:
            status = PipelineStatus.PARTIAL_SUCCESS
            errors = [
                f"Validation issue: {', '.join(validation.checks_failed)}"
            ]
        else:
            status = PipelineStatus.SUCCESS
            errors = []

        # Build download URL (resolved by the API routes layer)
        download_url: str | None = None
        if result_filename:
            download_url = f"/api/pipeline/download/{sid}/{result_filename}"

        return PipelineOutput(
            session_id=sid,
            status=status,
            summary=summary,
            result_file_path=result_file_path,
            result_filename=result_filename,
            download_url=download_url,
            preview_rows=preview_rows,
            preview_columns=preview_columns,
            total_rows=total_rows,
            chart_paths=chart_paths,
            executed_plan=plan,
            validation=validation,
            errors=errors,
        )

    def run_batch(
        self,
        uploaded_files: list[tuple[bytes | BinaryIO | Path | UploadFile, str]],
        prompt: str,
        session_id: str | None = None,
        export_format: str = _DEFAULT_EXPORT_FORMAT,
        raise_on_error: bool = False,
    ) -> PipelineOutput:
        """Execute a batch request applying the prompt operation across multiple files."""
        if not uploaded_files:
            return self._error_output(session_id or "", "No files uploaded for batch processing.")

        if len(uploaded_files) == 1:
            file_obj, orig_name = uploaded_files[0]
            return self.run(
                uploaded_file=file_obj,
                original_filename=orig_name,
                prompt=prompt,
                session_id=session_id,
                export_format=export_format,
                raise_on_error=raise_on_error,
            )

        sid = session_id or str(uuid.uuid4())
        session_dir = self.sessions_dir / sid
        batch_in_dir = session_dir / "batch_inputs"
        batch_out_dir = session_dir / "batch_outputs"
        batch_in_dir.mkdir(parents=True, exist_ok=True)
        batch_out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save all uploaded files safely
        saved_items: list[tuple[Path, str]] = []
        for idx, (uf, orig_name) in enumerate(uploaded_files):
            clean_name = Path(orig_name).name.replace("..", "_") or f"file_{idx}"
            dest = batch_in_dir / f"{idx}_{clean_name}"
            if isinstance(uf, bytes):
                dest.write_bytes(uf)
            elif hasattr(uf, "file") and hasattr(uf.file, "read"):
                uf.file.seek(0)
                dest.write_bytes(uf.file.read())
            elif hasattr(uf, "read"):
                if hasattr(uf, "seek"):
                    uf.seek(0)
                content = uf.read()
                if isinstance(content, str):
                    dest.write_text(content, encoding="utf-8")
                else:
                    dest.write_bytes(content)
            elif isinstance(uf, Path):
                shutil.copy2(uf, dest)
            saved_items.append((dest, clean_name))

        # 2. Detect categories
        detected_items = []
        for dest, clean_name in saved_items:
            det = detect_file(dest, clean_name)
            detected_items.append((dest, clean_name, det.detected_category))

        # 3. Determine target operation category
        prompt_lower = prompt.lower()
        target_category: FileCategory | None = None
        if any(w in prompt_lower for w in ("resize", "crop", "rotate", "compress image", "image", "photo", "jpg", "png", "dimension")):
            target_category = FileCategory.IMAGE
        elif any(w in prompt_lower for w in ("clean", "filter", "column", "row", "csv", "xlsx", "table", "tabular", "combine", "top 10", "aggregate", "sort")):
            target_category = FileCategory.TABULAR
        elif any(w in prompt_lower for w in ("extract text", "summarize", "document", "pdf", "docx", "word count")):
            target_category = FileCategory.DOCUMENT
        elif any(w in prompt_lower for w in ("audio", "sound", "trim audio", "wav", "mp3")):
            target_category = FileCategory.AUDIO
        elif any(w in prompt_lower for w in ("video", "frame", "mp4", "mov", "clip")):
            target_category = FileCategory.VIDEO
        else:
            unique_cats = {c for _, _, c in detected_items}
            if len(unique_cats) == 1:
                target_category = next(iter(unique_cats))

        # 4. Process each file
        batch_results: list[BatchItemResult] = []
        successful_outputs: list[tuple[Path, str]] = []

        for dest, clean_name, cat in detected_items:
            if target_category is not None and cat != target_category:
                batch_results.append(
                    BatchItemResult(
                        filename=clean_name,
                        status="excluded",
                        category=cat.value,
                        reason=f"{cat.value.capitalize()} file excluded: incompatible with requested {target_category.value} operation.",
                        output_filename=None,
                        validation_passed=None,
                        details={"expected": target_category.value, "actual": cat.value},
                    )
                )
                continue

            try:
                processor = get_processor(cat)
                prof_dict = processor.profile(dest, session_id=sid)
                prof_obj = DataProfile(**prof_dict)
                objectives = parse_intent(prompt, prof_obj, llm_client=self.llm_client)
                plan = build_plan(objectives, prof_obj, session_id=sid, llm_client=self.llm_client)

                item_out = batch_out_dir / f"out_{len(successful_outputs)}"
                item_out.mkdir(parents=True, exist_ok=True)
                after_state = processor.execute(dest, plan, output_dir=item_out)

                val = processor.validate_output(before_state=dest, after_state=after_state, structured_operation=plan)
                if not val.is_valid:
                    batch_results.append(
                        BatchItemResult(
                            filename=clean_name,
                            status="failed",
                            category=cat.value,
                            reason=f"Validation failed: {', '.join(val.checks_failed)}",
                            output_filename=None,
                            validation_passed=False,
                            details=val.details,
                        )
                    )
                    continue

                out_fmt = export_format if cat == FileCategory.TABULAR else dest.suffix.lstrip(".")
                exported_path = processor.export(
                    state=after_state,
                    output_format=out_fmt,
                    output_dir=item_out,
                    filename_stem=Path(clean_name).stem + "_processed",
                )
                arcname = f"{Path(clean_name).stem}_processed{exported_path.suffix}"
                successful_outputs.append((exported_path, arcname))
                batch_results.append(
                    BatchItemResult(
                        filename=clean_name,
                        status="success",
                        category=cat.value,
                        reason=None,
                        output_filename=arcname,
                        validation_passed=True,
                        details={"size": f"{exported_path.stat().st_size} bytes"},
                    )
                )
            except Exception as exc:
                log.exception("Error processing batch item '%s': %s", clean_name, exc)
                batch_results.append(
                    BatchItemResult(
                        filename=clean_name,
                        status="failed",
                        category=cat.value,
                        reason=str(exc),
                        output_filename=None,
                        validation_passed=False,
                        details={"error": str(exc)},
                    )
                )

        # 5. Summary metrics
        total_files = len(uploaded_files)
        succeeded = sum(1 for r in batch_results if r.status == "success")
        failed = sum(1 for r in batch_results if r.status == "failed")
        excluded = sum(1 for r in batch_results if r.status == "excluded")
        processed = succeeded + failed

        batch_summary = BatchSummary(
            total_files=total_files,
            processed_count=processed,
            succeeded_count=succeeded,
            failed_count=failed,
            excluded_count=excluded,
        )

        # 6. Package result files into ZIP
        result_file_path: str | None = None
        result_filename: str | None = None
        download_url: str | None = None

        if len(successful_outputs) > 1:
            zip_dest = session_dir / "result.zip"
            create_safe_archive(successful_outputs, zip_dest, archive_format="zip")
            result_file_path = str(zip_dest)
            result_filename = "result.zip"
            download_url = f"/api/pipeline/download/{sid}/result.zip"
        elif len(successful_outputs) == 1:
            single_path, single_name = successful_outputs[0]
            final_dest = session_dir / single_name
            if single_path != final_dest:
                shutil.copy2(single_path, final_dest)
            result_file_path = str(final_dest)
            result_filename = final_dest.name
            download_url = f"/api/pipeline/download/{sid}/{result_filename}"

        # 7. Status & Summary
        if succeeded == total_files:
            status = PipelineStatus.SUCCESS
        elif succeeded > 0:
            status = PipelineStatus.PARTIAL_SUCCESS
        else:
            status = PipelineStatus.FAILED

        parts = [f"Batch processed {total_files} file(s): {succeeded} succeeded, {failed} failed, {excluded} excluded."]
        if excluded > 0:
            excl_names = [f"{r.filename} ({r.reason})" for r in batch_results if r.status == "excluded"]
            parts.append(f"Excluded: {'; '.join(excl_names)}.")
        if result_filename:
            parts.append(f"Result files packaged into {result_filename}.")
        summary_text = " ".join(parts)

        # Preview table
        preview_columns = ["Filename", "Category", "Status", "Details"]
        preview_rows = [
            {
                "Filename": r.filename,
                "Category": r.category.upper(),
                "Status": r.status.upper(),
                "Details": r.reason or (f"Processed: {r.output_filename}" if r.output_filename else "OK"),
            }
            for r in batch_results
        ]

        return PipelineOutput(
            session_id=sid,
            status=status,
            summary=summary_text,
            result_file_path=result_file_path,
            result_filename=result_filename,
            download_url=download_url,
            preview_rows=preview_rows,
            preview_columns=preview_columns,
            total_rows=total_files,
            chart_paths=[],
            executed_plan=None,
            validation=None,
            errors=[r.reason for r in batch_results if r.status == "failed" and r.reason],
            batch_results=batch_results,
            batch_summary=batch_summary,
        )

