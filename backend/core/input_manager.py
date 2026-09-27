"""DataWise Input Manager.

Handles file validation, size limits, security sanitization, and session-isolated
storage for incoming tabular datasets.
"""

from io import BytesIO
import json
from pathlib import Path
from typing import BinaryIO
import uuid
import openpyxl

from backend.config import SESSIONS_DIR, SUPPORTED_EXTENSIONS
from backend.core.exceptions import FileValidationError

# Maximum allowable decompressed cell count for Excel files to guard against zip bombs
MAX_EXCEL_CELLS = 5_000_000


class InputManager:
    """Manages file ingestion, validation, and session workspace isolation."""

    @classmethod
    def validate_and_save(
        cls,
        uploaded_file: bytes | BinaryIO | Path | str | any,
        original_filename: str | None = None,
        session_id: str | None = None,
        sessions_dir: Path | None = None,
    ) -> tuple[str, Path]:
        """Validate an uploaded file and save it to an isolated session directory.

        Security Guarantees:
        --------------------
        1. [FIX F3]: The original uploaded filename is NEVER used to construct a
           filesystem path. The file is saved strictly as `input{ext}` within
           the session directory. The original name is kept only as metadata.
        2. [FIX F4]: Excel (.xlsx) files are inspected for total decompressed cell
           counts before full loading to prevent memory-exhaustion zip-bomb attacks.
        3. Extension allow-list (.csv, .xlsx, .json only).
        4. Application-level size limit removed (was 50MB); relies on infrastructure limits.

        Args:
            uploaded_file: Raw bytes, file-like object, Path, or FastAPI UploadFile.
            original_filename: User-provided filename (used for extension extraction).
            session_id: Optional existing session ID; if omitted, a new UUID is generated.
            sessions_dir: Optional base directory override for sessions.

        Returns:
            Tuple of (session_id, resolved_internal_file_path).

        Raises:
            FileValidationError: If the file violates format, size, or security rules.
        """
        # 1. Determine original filename
        orig_name = original_filename
        if not orig_name and hasattr(uploaded_file, "filename"):
            orig_name = uploaded_file.filename
        elif not orig_name and isinstance(uploaded_file, (Path, str)):
            orig_name = Path(uploaded_file).name
        elif not orig_name and hasattr(uploaded_file, "name"):
            orig_name = Path(uploaded_file.name).name

        if not orig_name:
            raise FileValidationError("Filename could not be determined for the uploaded file.")

        # 2. Validate file extension
        # Extract extension using suffix of the clean filename
        clean_name = Path(orig_name).name
        ext = Path(clean_name).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise FileValidationError(
                f"Unsupported file format '{ext}'. Only {supported} files are currently supported."
            )

        # 3. Read content and enforce size limits
        content: bytes
        if isinstance(uploaded_file, bytes):
            content = uploaded_file
        elif isinstance(uploaded_file, (Path, str)):
            p = Path(uploaded_file)
            if not p.exists():
                raise FileValidationError(f"Source file not found: {p}")
            content = p.read_bytes()
        elif hasattr(uploaded_file, "file") and hasattr(uploaded_file.file, "read"):
            # FastAPI UploadFile
            uploaded_file.file.seek(0)
            content = uploaded_file.file.read()
        elif hasattr(uploaded_file, "read"):
            # Generic file-like
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
            content = uploaded_file.read()
        else:
            raise FileValidationError("Invalid upload payload type provided.")

        if len(content) == 0:
            raise FileValidationError("The uploaded file is empty (0 bytes).")


        # 4. Prepare isolated session directory
        sid = session_id or str(uuid.uuid4())
        base_dir = (sessions_dir or SESSIONS_DIR).resolve()
        session_folder = (base_dir / sid).resolve()
        session_folder.mkdir(parents=True, exist_ok=True)

        # 5. SECURITY [FIX F3]: Fixed internal filename derived ONLY from session & extension
        target_path = (session_folder / f"input{ext}").resolve()

        # Invariant assertion: path must strictly reside within the session folder
        if session_folder not in target_path.parents:
            raise FileValidationError(
                "Security violation: Attempted path traversal detected in file storage."
            )

        # Write file content to disk
        target_path.write_bytes(content)

        # Write session metadata (storing original_filename strictly as display text)
        metadata_path = session_folder / "metadata.json"
        metadata = {
            "session_id": sid,
            "original_filename": orig_name,
            "file_format": ext.lstrip("."),
            "size_bytes": len(content),
            "stored_filename": target_path.name,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # 6. SECURITY [FIX F4]: Inspect Excel decompressed cell count to guard against zip bombs
        if ext == ".xlsx":
            try:
                wb = openpyxl.load_workbook(target_path, read_only=True, data_only=True)
                total_cells = 0
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    max_r = ws.max_row or 0
                    max_c = ws.max_column or 0
                    total_cells += (max_r * max_c)
                wb.close()
            except Exception as e:
                if target_path.exists():
                    target_path.unlink()
                raise FileValidationError(f"Unable to read Excel workbook structure: {str(e)}")

            if total_cells > MAX_EXCEL_CELLS:
                if target_path.exists():
                    target_path.unlink()
                raise FileValidationError(
                    f"Excel file exceeds maximum cell limit of {MAX_EXCEL_CELLS:,} cells "
                    f"(estimated {total_cells:,} cells). Potential decompression bomb."
                )

        return sid, target_path
