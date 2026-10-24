"""DataWise API Routes.

Exposes the DataWise pipeline over HTTP:
  POST /api/pipeline/run                        — Upload file + prompt → PipelineOutput JSON
  GET  /api/pipeline/download/{session_id}/{fn} — Path-safe result file download
  GET  /api/download/{session_id}/{fn}          — Alias for result file download
  GET  /api/session/{session_id}/status         — Session metadata

SECURITY CONTRACT:
  - File download is strictly path-safe: the filename is validated against the
    session directory BEFORE any filesystem operations. No path traversal is possible.
  - The session_id is validated as a UUID4. No directory traversal.
  - Errors are always mapped to structured JSON; raw stack traces are never surfaced.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from backend.config import REPO_ROOT, SESSIONS_DIR
from backend.core.exceptions import (
    DataWiseError,
    DataWiseValidationError,
    ExecutionError,
    FileValidationError,
    LLMBudgetExceededError,
    ParsingError,
    ToolInputError,
)
from backend.core.executor import ExecutorError
from backend.core.pipeline import DataWisePipeline
from backend.models.schemas import ErrorResponse, PipelineOutput

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Pipeline"])

# Session ID must be a standard UUID4 — anything else is rejected outright.
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Allowed result filename stems + extensions for download endpoint
_ALLOWED_FILENAME_RE = re.compile(
    r"^([a-zA-Z0-9_.-]+\.(csv|xlsx|json|txt|md|jpg|jpeg|png|gif|webp|bmp|tiff|tif|wav|mp3|mp4|mov|avi|mkv|webm|zip|tar|gz))$",
    re.IGNORECASE,
)


def _validate_session_id(session_id: str) -> None:
    """Raise 400 if session_id is not a valid UUID4 or contains traversal tokens."""
    if any(seq in session_id for seq in ("..", "/", "\\")):
        raise HTTPException(
            status_code=400,
            detail="Path traversal characters detected in session_id.",
        )
    if not _UUID_RE.match(session_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid session_id format. Must be a valid UUID4.",
        )


@router.post(
    "/pipeline/run",
    response_model=PipelineOutput,
    responses={
        400: {"model": ErrorResponse, "description": "Client file validation or tool input error"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "LLM call budget exceeded"},
        500: {"model": ErrorResponse, "description": "Execution or internal server error"},
    },
    summary="Run the full DataWise pipeline",
    description=(
        "Upload one or more files and provide a natural-language instruction. "
        "Returns a PipelineOutput with status, summary, preview, chart paths, "
        "and a download URL for the processed file or packaged batch archive."
    ),
)
async def run_pipeline(
    file: UploadFile | None = File(default=None, description="Single file upload"),
    files: list[UploadFile] | None = File(default=None, description="Multi-file batch upload"),
    prompt: str = Form(..., description="Natural-language processing instruction"),
    session_id: str | None = Form(default=None, description="Optional existing session ID"),
    export_format: str = Form(default="csv", description="Output format: csv, xlsx, json, or archive"),
    api_key: str | None = Form(default=None, description="Optional LLM API key override"),
    provider: str | None = Form(default=None, description="Optional LLM provider override (gemini/anthropic/openai)"),
) -> PipelineOutput | JSONResponse:
    """Execute the full DataWise pipeline for single or multi-file uploads."""
    if session_id:
        _validate_session_id(session_id)

    # Gather all uploaded files
    uploaded_list: list[UploadFile] = []
    if files:
        uploaded_list.extend(files)
    if file:
        uploaded_list.append(file)

    if not uploaded_list:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "status": "error",
                "error_code": "FILE_VALIDATION_ERROR",
                "message": "No file was uploaded.",
                "details": None,
            },
        )

    from backend.core.llm_provider import get_default_llm_provider
    llm_client = get_default_llm_provider(explicit_key=api_key, explicit_provider=provider)
    pipeline = DataWisePipeline(llm_client=llm_client)

    try:
        if len(uploaded_list) == 1:
            target_file = uploaded_list[0]
            output = pipeline.run(
                uploaded_file=target_file,
                original_filename=target_file.filename or "upload",
                prompt=prompt,
                session_id=session_id,
                export_format=export_format,
                raise_on_error=True,
            )
        else:
            batch_files = [(f, f.filename or f"upload_{i}") for i, f in enumerate(uploaded_list)]
            output = pipeline.run_batch(
                uploaded_files=batch_files,
                prompt=prompt,
                session_id=session_id,
                export_format=export_format,
                raise_on_error=True,
            )
        return output
    except (FileValidationError, ParsingError) as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "status": "error",
                "error_code": "FILE_VALIDATION_ERROR",
                "message": exc.message,
                "details": exc.details,
            },
        )
    except ToolInputError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "status": "error",
                "error_code": "TOOL_INPUT_ERROR",
                "message": exc.message,
                "details": exc.details,
            },
        )
    except LLMBudgetExceededError as exc:
        return JSONResponse(
            status_code=429,
            content={
                "error": True,
                "status": "error",
                "error_code": "LLM_BUDGET_EXCEEDED",
                "message": str(exc),
                "details": getattr(exc, "details", None),
            },
        )
    except (ExecutorError, ExecutionError) as exc:
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "status": "error",
                "error_code": "EXECUTION_ERROR",
                "message": getattr(exc, "message", str(exc)),
                "details": getattr(exc, "details", None),
            },
        )
    except DataWiseValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={
                "error": True,
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": getattr(exc, "message", str(exc)),
                "details": getattr(exc, "details", None),
            },
        )
    except DataWiseError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "status": "error",
                "error_code": getattr(exc, "error_code", "DATAWISE_ERROR"),
                "message": getattr(exc, "message", str(exc)),
                "details": getattr(exc, "details", None),
            },
        )
    except ValueError as exc:
        log.warning("Operation validation or execution issue: %s", exc)
        return JSONResponse(
            status_code=400,
            content={
                "error": True,
                "status": "error",
                "error_code": "UNSUPPORTED_OPERATION",
                "message": str(exc),
                "details": None,
            },
        )
    except Exception as exc:
        log.exception("Unhandled error in run_pipeline endpoint: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "status": "error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred during processing.",
                "details": None,
            },
        )


@router.get(
    "/pipeline/download/{session_id}/{filename}",
    response_class=FileResponse,
    summary="Download a processed result file (canonical route)",
    description="Serve a result file strictly verified against path traversal.",
)
@router.get(
    "/download/{session_id}/{filename}",
    response_class=FileResponse,
    include_in_schema=False,
    summary="Download a processed result file (alias)",
)
async def download_result(
    session_id: str,
    filename: str,
) -> FileResponse:
    """Serve a result file from the session workspace.

    PATH-SAFETY CONTRACT [FIX F3]:
      1. Pre-filesystem checks: Reject traversal sequences ('..', '/', '\\') immediately.
      2. session_id is validated against a strict UUID4 regex.
      3. filename is validated against an allow-list pattern (result.csv|xlsx|json, *.png).
      4. The resolved path is asserted to stay strictly inside workspace/sessions/.
      If any check fails, HTTP 400 or 403 is returned with NO filesystem exposure.
    """
    # 1. Pre-filesystem checks for traversal tokens
    if any(seq in session_id for seq in ("..", "/", "\\")):
        raise HTTPException(
            status_code=400,
            detail="Path traversal sequence detected in session_id.",
        )
    if any(seq in filename for seq in ("..", "/", "\\")):
        raise HTTPException(
            status_code=400,
            detail="Path traversal sequence detected in filename.",
        )

    # 2. Validate session_id format
    _validate_session_id(session_id)

    # 3. Validate filename against allow-list
    if not _ALLOWED_FILENAME_RE.match(filename):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid filename '{filename}'. "
                "Only result.csv, result.xlsx, result.json, and chart images are downloadable."
            ),
        )

    # 4. Resolve path and assert containment strictly within session_dir & SESSIONS_DIR
    session_dir = (SESSIONS_DIR / session_id).resolve()
    target_path = (session_dir / filename).resolve()

    sessions_root = SESSIONS_DIR.resolve()
    if not target_path.is_relative_to(session_dir) or not target_path.is_relative_to(sessions_root):
        raise HTTPException(
            status_code=403,
            detail="Access denied: path traversal attempt detected.",
        )

    if not target_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Result file '{filename}' not found for session {session_id}.",
        )

    media_type = "application/octet-stream"
    if filename.endswith(".csv"):
        media_type = "text/csv"
    elif filename.endswith(".json"):
        media_type = "application/json"
    elif filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.endswith(".png"):
        media_type = "image/png"
    elif filename.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif filename.endswith(".webp"):
        media_type = "image/webp"
    elif filename.endswith(".gif"):
        media_type = "image/gif"
    elif filename.endswith(".bmp"):
        media_type = "image/bmp"
    elif filename.endswith((".tiff", ".tif")):
        media_type = "image/tiff"
    elif filename.endswith(".txt"):
        media_type = "text/plain"
    elif filename.endswith(".md"):
        media_type = "text/markdown"
    elif filename.endswith(".wav"):
        media_type = "audio/wav"
    elif filename.endswith(".mp3"):
        media_type = "audio/mpeg"
    elif filename.endswith(".mp4"):
        media_type = "video/mp4"
    elif filename.endswith(".mov"):
        media_type = "video/quicktime"
    elif filename.endswith(".avi"):
        media_type = "video/x-msvideo"
    elif filename.endswith(".mkv"):
        media_type = "video/x-matroska"
    elif filename.endswith(".webm"):
        media_type = "video/webm"

    return FileResponse(
        path=str(target_path),
        filename=filename,
        media_type=media_type,
    )


@router.get(
    "/session/{session_id}/status",
    summary="Get session metadata",
)
async def get_session_status(session_id: str) -> dict:
    """Return session metadata (exists, has result file, etc.)."""
    _validate_session_id(session_id)

    session_dir = (SESSIONS_DIR / session_id).resolve()
    if not session_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )

    metadata_path = session_dir / "metadata.json"
    result_files = [
        p.name for p in session_dir.iterdir()
        if p.suffix in {".csv", ".xlsx", ".json", ".png"} and p.stem == "result"
    ]

    return {
        "session_id": session_id,
        "exists": True,
        "has_result": bool(result_files),
        "result_files": result_files,
        "has_metadata": metadata_path.exists(),
    }


@router.get(
    "/capabilities",
    summary="Get live platform capabilities and supported formats",
)
async def get_capabilities() -> dict:
    """Return live platform capabilities, supported formats, and active processors.

    Dynamically reads capabilities.json and checks ProcessorRegistry so frontend
    and clients never drift from backend reality.
    """
    import json
    from backend.core.file_detection import CATEGORY_EXTENSIONS
    from backend.processors.registry import list_registered_categories

    cap_path = REPO_ROOT / "capabilities.json"
    raw_caps = {}
    if cap_path.exists():
        try:
            raw_caps = json.loads(cap_path.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Failed to parse capabilities.json: %s", exc)

    registered_cats = list_registered_categories()
    processors_info = raw_caps.get("processors", {})
    supported_extensions: list[str] = []
    extensions_by_category: dict[str, list[str]] = {}
    active_categories: list[str] = []

    for cat in registered_cats:
        cat_str = cat.value
        proc_meta = processors_info.get(cat_str, {})
        is_supported = proc_meta.get("supported", True)
        if is_supported:
            active_categories.append(cat_str)
            exts = CATEGORY_EXTENSIONS.get(cat, [])
            extensions_by_category[cat_str] = exts
            supported_extensions.extend(exts)

    return {
        "supported_extensions": supported_extensions,
        "extensions_by_category": extensions_by_category,
        "supported_categories": active_categories,
        "processors": processors_info,
    }


@router.get(
    "/llm/status",
    summary="Get active LLM provider status",
    description="Check whether an LLM provider is active or if deterministic fallback is in use.",
)
async def get_llm_status() -> dict[str, Any]:
    """Return active LLM provider name and supported providers."""
    from backend.core.llm_provider import get_default_llm_provider
    provider = get_default_llm_provider()
    return {
        "active": provider is not None,
        "provider_name": provider.get_provider_name() if provider else "Deterministic Heuristic Engine",
        "supported_providers": ["gemini", "anthropic", "openai", "local_openai"],
    }


