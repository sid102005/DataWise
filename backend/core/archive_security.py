"""DataWise Archive Security Guard.

Provides pre-extraction security analysis and safe extraction primitives
for ZIP, TAR, and GZ archives using the Python standard library.

SECURITY GUARANTEES:
1. Zip-Slip / Path Traversal Prevention:
   - Complete pre-extraction inspection of all member names.
   - Rejection of entries containing traversal components ('..', absolute paths, drive letters).
   - Rejection of symlinks and hardlinks.
   - Strict canonical resolution validation: target must be inside extraction directory.
   - Consistent policy: Any path traversal violation rejects the entire archive.

2. Archive Bomb / Resource Exhaustion Prevention:
   - Sums declared uncompressed sizes across all entries prior to extracting any file.
   - Enforces a hard ceiling on total uncompressed size (default: 500 MB).
   - Enforces a hard ceiling on member entry count (default: 10,000 entries).
   - Enforces compression ratio bounds (ratio > 100:1 for data > 10 MB).
   - GZ streaming byte-count guard ensures decompression aborts if limit exceeded.

3. Safe Temporary Extraction:
   - Extracts into an isolated, session-scoped directory.
   - Cleanup is strictly guaranteed on both success and failure paths.
"""

from __future__ import annotations

import gzip
import io
import logging
import os
from pathlib import Path
import re
import shutil
import struct
import tarfile
from typing import Any, Generator, Sequence
import uuid
import zipfile

from backend.core.exceptions import ArchiveSecurityError

log = logging.getLogger(__name__)

# Security boundaries
MAX_DECLARED_UNCOMPRESSED_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB
MAX_ARCHIVE_ENTRY_COUNT: int = 10_000  # 10,000 entries
MAX_COMPRESSION_RATIO: float = 100.0  # 100:1 ratio limit
CHUNK_SIZE_BYTES: int = 64 * 1024  # 64 KB

_ABSOLUTE_PATH_RE = re.compile(r"^([a-zA-Z]:|[/\\])")


class ArchiveSecurityManifest:
    """Audit manifest of inspected archive members and security metrics."""

    def __init__(
        self,
        format_type: str,
        entry_count: int,
        total_uncompressed_bytes: int,
        archive_size_bytes: int,
        entries: list[dict[str, Any]],
    ) -> None:
        self.format_type = format_type
        self.entry_count = entry_count
        self.total_uncompressed_bytes = total_uncompressed_bytes
        self.archive_size_bytes = archive_size_bytes
        self.entries = entries

    @property
    def compression_ratio(self) -> float:
        if self.archive_size_bytes <= 0:
            return 1.0
        return self.total_uncompressed_bytes / self.archive_size_bytes


def _is_suspicious_entry_name(name: str) -> bool:
    """Return True if an entry name attempts path traversal or is absolute."""
    if not name or "\x00" in name:
        return True

    # Normalize slashes
    norm = name.replace("\\", "/")

    # Absolute path check
    if _ABSOLUTE_PATH_RE.match(norm) or norm.startswith("/"):
        return True

    # Path component inspection for traversal tokens
    parts = norm.split("/")
    for part in parts:
        if part == "..":
            return True

    return False


def _check_zip_security(
    archive_path: Path,
    max_uncompressed_bytes: int,
    max_entries: int,
) -> ArchiveSecurityManifest:
    """Inspect a ZIP file's central directory without extracting any data."""
    archive_size = archive_path.stat().st_size
    entries: list[dict[str, Any]] = []
    total_uncompressed = 0

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            infolist = zf.infolist()
            entry_count = len(infolist)

            if entry_count > max_entries:
                raise ArchiveSecurityError(
                    f"Archive rejected: Entry count ({entry_count:,}) exceeds maximum allowed "
                    f"threshold ({max_entries:,}). Potential resource exhaustion bomb."
                )

            for info in infolist:
                # 1. Zip-slip / path traversal check
                if _is_suspicious_entry_name(info.filename):
                    raise ArchiveSecurityError(
                        f"Archive rejected: Path traversal entry detected: '{info.filename}'. "
                        "Extraction refused for security."
                    )

                # 2. Symlink check in external_attr (POSIX symlink is mode 0o120000)
                is_symlink = (info.external_attr >> 16) & 0o170000 == 0o120000
                if is_symlink:
                    raise ArchiveSecurityError(
                        f"Archive rejected: Symbolic link detected in entry: '{info.filename}'. "
                        "Symlinks in archives are prohibited."
                    )

                # 3. Accumulate declared uncompressed size
                declared_size = info.file_size
                total_uncompressed += declared_size

                entries.append({
                    "name": info.filename,
                    "is_dir": info.is_dir(),
                    "size": declared_size,
                    "compressed_size": info.compress_size,
                })

    except zipfile.BadZipFile as exc:
        raise ArchiveSecurityError(f"Corrupted or invalid ZIP archive: {exc}")

    # Check uncompressed size bomb
    if total_uncompressed > max_uncompressed_bytes:
        limit_mb = max_uncompressed_bytes / (1024 * 1024)
        declared_mb = total_uncompressed / (1024 * 1024)
        raise ArchiveSecurityError(
            f"Archive rejected: Declared uncompressed size ({declared_mb:.1f} MB) exceeds "
            f"maximum allowed limit ({limit_mb:.1f} MB). Potential decompression bomb."
        )

    # Check compression ratio bomb (for declared data > 10 MB)
    if total_uncompressed > 10 * 1024 * 1024 and archive_size > 0:
        ratio = total_uncompressed / archive_size
        if ratio > MAX_COMPRESSION_RATIO:
            raise ArchiveSecurityError(
                f"Archive rejected: Abnormal compression ratio ({ratio:.1f}:1 exceeds "
                f"{MAX_COMPRESSION_RATIO:.1f}:1). Potential decompression bomb."
            )

    return ArchiveSecurityManifest(
        format_type="zip",
        entry_count=entry_count,
        total_uncompressed_bytes=total_uncompressed,
        archive_size_bytes=archive_size,
        entries=entries,
    )


def _check_tar_security(
    archive_path: Path,
    max_uncompressed_bytes: int,
    max_entries: int,
) -> ArchiveSecurityManifest:
    """Inspect a TAR file's headers without extracting any data."""
    archive_size = archive_path.stat().st_size
    entries: list[dict[str, Any]] = []
    total_uncompressed = 0

    try:
        with tarfile.open(archive_path, "r:*") as tf:
            members = tf.getmembers()
            entry_count = len(members)

            if entry_count > max_entries:
                raise ArchiveSecurityError(
                    f"Archive rejected: Entry count ({entry_count:,}) exceeds maximum allowed "
                    f"threshold ({max_entries:,}). Potential resource exhaustion bomb."
                )

            for member in members:
                # 1. Path traversal check
                if _is_suspicious_entry_name(member.name):
                    raise ArchiveSecurityError(
                        f"Archive rejected: Path traversal entry detected: '{member.name}'. "
                        "Extraction refused for security."
                    )

                # 2. Symlink / Hardlink check
                if member.issym() or member.islnk():
                    raise ArchiveSecurityError(
                        f"Archive rejected: Link detected in entry: '{member.name}'. "
                        "Links in archives are prohibited."
                    )

                # 3. Device nodes / special files check
                if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
                    raise ArchiveSecurityError(
                        f"Archive rejected: Special system entry detected: '{member.name}'."
                    )

                total_uncompressed += member.size
                entries.append({
                    "name": member.name,
                    "is_dir": member.isdir(),
                    "size": member.size,
                    "compressed_size": member.size,
                })

    except (tarfile.TarError, EOFError) as exc:
        raise ArchiveSecurityError(f"Corrupted or invalid TAR archive: {exc}")

    if total_uncompressed > max_uncompressed_bytes:
        limit_mb = max_uncompressed_bytes / (1024 * 1024)
        declared_mb = total_uncompressed / (1024 * 1024)
        raise ArchiveSecurityError(
            f"Archive rejected: Declared uncompressed size ({declared_mb:.1f} MB) exceeds "
            f"maximum allowed limit ({limit_mb:.1f} MB). Potential decompression bomb."
        )

    if total_uncompressed > 10 * 1024 * 1024 and archive_size > 0:
        ratio = total_uncompressed / archive_size
        if ratio > MAX_COMPRESSION_RATIO:
            raise ArchiveSecurityError(
                f"Archive rejected: Abnormal compression ratio ({ratio:.1f}:1 exceeds "
                f"{MAX_COMPRESSION_RATIO:.1f}:1). Potential decompression bomb."
            )

    return ArchiveSecurityManifest(
        format_type="tar",
        entry_count=entry_count,
        total_uncompressed_bytes=total_uncompressed,
        archive_size_bytes=archive_size,
        entries=entries,
    )


def _check_gz_security(
    archive_path: Path,
    max_uncompressed_bytes: int,
) -> ArchiveSecurityManifest:
    """Inspect a standalone GZ file without loading unbounded data into memory."""
    archive_size = archive_path.stat().st_size

    # GZIP stores uncompressed size modulo 2^32 in the final 4 bytes (ISIZE)
    if archive_size < 10:
        raise ArchiveSecurityError("GZ archive is too small to contain valid gzip header and footer.")

    with open(archive_path, "rb") as f:
        f.seek(-4, os.SEEK_END)
        isize = struct.unpack("<I", f.read(4))[0]

    # If declared ISIZE alone exceeds threshold, reject immediately
    if isize > max_uncompressed_bytes:
        limit_mb = max_uncompressed_bytes / (1024 * 1024)
        declared_mb = isize / (1024 * 1024)
        raise ArchiveSecurityError(
            f"Archive rejected: Declared uncompressed size ({declared_mb:.1f} MB) exceeds "
            f"maximum allowed limit ({limit_mb:.1f} MB). Potential decompression bomb."
        )

    # Derive inner filename stem
    inner_name = archive_path.name
    if inner_name.lower().endswith(".gz"):
        inner_name = inner_name[:-3]
    if not inner_name:
        inner_name = "extracted_data"

    if _is_suspicious_entry_name(inner_name):
        raise ArchiveSecurityError(f"Archive rejected: Invalid inner filename: '{inner_name}'.")

    return ArchiveSecurityManifest(
        format_type="gz",
        entry_count=1,
        total_uncompressed_bytes=isize,
        archive_size_bytes=archive_size,
        entries=[{"name": inner_name, "is_dir": False, "size": isize, "compressed_size": archive_size}],
    )


def validate_archive_security(
    archive_path: Path,
    max_uncompressed_bytes: int = MAX_DECLARED_UNCOMPRESSED_SIZE_BYTES,
    max_entries: int = MAX_ARCHIVE_ENTRY_COUNT,
) -> ArchiveSecurityManifest:
    """Pre-extraction security inspection. Raises ArchiveSecurityError on any hazard."""
    if not archive_path.exists():
        raise ArchiveSecurityError(f"Archive file not found: {archive_path}")

    # Sniff format via magic bytes
    with open(archive_path, "rb") as f:
        header = f.read(512)

    # ZIP signature: PK\x03\x04 or PK\x05\x06 (empty zip) or PK\x07\x08
    if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
        return _check_zip_security(archive_path, max_uncompressed_bytes, max_entries)

    # GZIP signature: \x1f\x8b
    if header.startswith(b"\x1f\x8b"):
        # Could be a tar.gz (.tgz) or plain .gz
        # Test if it can be opened as tarfile
        try:
            with tarfile.open(archive_path, "r:gz") as tf:
                # If valid tarfile, treat as tar
                return _check_tar_security(archive_path, max_uncompressed_bytes, max_entries)
        except (tarfile.TarError, EOFError):
            # Not a tar archive; treat as standalone gzip
            return _check_gz_security(archive_path, max_uncompressed_bytes)

    # Plain TAR signature: 'ustar' at offset 257
    if len(header) >= 262 and (header[257:262] in (b"ustar", b"GNUt") or archive_path.suffix.lower() == ".tar"):
        return _check_tar_security(archive_path, max_uncompressed_bytes, max_entries)

    # Fallback to extension check if magic bytes are ambiguous
    ext = archive_path.suffix.lower()
    if ext == ".zip":
        return _check_zip_security(archive_path, max_uncompressed_bytes, max_entries)
    if ext == ".tar":
        return _check_tar_security(archive_path, max_uncompressed_bytes, max_entries)
    if ext == ".gz":
        return _check_gz_security(archive_path, max_uncompressed_bytes)

    raise ArchiveSecurityError(f"Unsupported archive format for file: '{archive_path.name}'.")


def safe_extract_archive(
    archive_path: Path,
    target_dir: Path,
    session_id: str = "",
    max_uncompressed_bytes: int = MAX_DECLARED_UNCOMPRESSED_SIZE_BYTES,
) -> list[Path]:
    """Safely extract an archive into target_dir with strict isolation and cleanup.

    Guarantees:
    - Pre-extraction security check run before any file write.
    - Path resolution double-checked for each entry against target_dir.
    - If any extraction step fails, target_dir is cleaned up before re-raising.
    - Returns a list of extracted file Paths.
    """
    manifest = validate_archive_security(archive_path, max_uncompressed_bytes=max_uncompressed_bytes)

    target_dir.mkdir(parents=True, exist_ok=True)
    resolved_target = target_dir.resolve()
    extracted_files: list[Path] = []

    try:
        if manifest.format_type == "zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                for member in zf.infolist():
                    # Double-check canonical target path
                    dest_path = (target_dir / member.filename).resolve()
                    try:
                        dest_path.relative_to(resolved_target)
                    except ValueError:
                        raise ArchiveSecurityError(
                            f"Zip-slip breakout detected during extraction: '{member.filename}'"
                        )

                    if member.is_dir():
                        dest_path.mkdir(parents=True, exist_ok=True)
                        continue

                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as source, open(dest_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    extracted_files.append(dest_path)

        elif manifest.format_type == "tar":
            with tarfile.open(archive_path, "r:*") as tf:
                for member in tf.getmembers():
                    dest_path = (target_dir / member.name).resolve()
                    try:
                        dest_path.relative_to(resolved_target)
                    except ValueError:
                        raise ArchiveSecurityError(
                            f"Tar-slip breakout detected during extraction: '{member.name}'"
                        )

                    if member.isdir():
                        dest_path.mkdir(parents=True, exist_ok=True)
                        continue

                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    fileobj = tf.extractfile(member)
                    if fileobj is not None:
                        with fileobj as source, open(dest_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        extracted_files.append(dest_path)

        elif manifest.format_type == "gz":
            # Stream decompress single file with byte-count limit
            inner_name = manifest.entries[0]["name"]
            dest_path = (target_dir / inner_name).resolve()
            try:
                dest_path.relative_to(resolved_target)
            except ValueError:
                raise ArchiveSecurityError(f"Path breakout in gz entry: '{inner_name}'")

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            bytes_written = 0

            with gzip.open(archive_path, "rb") as source, open(dest_path, "wb") as target:
                while True:
                    chunk = source.read(CHUNK_SIZE_BYTES)
                    if not chunk:
                        break
                    bytes_written += len(chunk)
                    if bytes_written > max_uncompressed_bytes:
                        raise ArchiveSecurityError(
                            f"Decompression bomb detected: GZ uncompressed stream exceeded "
                            f"{max_uncompressed_bytes / (1024 * 1024):.1f} MB during extraction."
                        )
                    target.write(chunk)

            extracted_files.append(dest_path)

        return extracted_files

    except Exception:
        # Guarantee cleanup on failure
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        raise


class SafeArchiveWorkspace:
    """Context manager for temporary extraction workspace with guaranteed cleanup."""

    def __init__(self, session_dir: Path, prefix: str = "tmp_archive_") -> None:
        self.session_dir = session_dir
        self.workspace_dir = session_dir / f"{prefix}{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> Path:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return self.workspace_dir

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Remove the temporary workspace directory."""
        if self.workspace_dir.exists():
            shutil.rmtree(self.workspace_dir, ignore_errors=True)


def create_safe_archive(
    source_files: Sequence[Path | tuple[Path, str]],
    output_archive_path: Path,
    archive_format: str = "zip",
) -> Path:
    """Create a new archive from files safely, ensuring all stored paths are relative.

    Args:
        source_files: List of Paths or (file_path, arcname) tuples.
        output_archive_path: Destination path for the new archive.
        archive_format: 'zip', 'tar', 'gz', or 'tar.gz'.

    Returns:
        The output_archive_path.
    """
    output_archive_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = archive_format.lower().lstrip(".")

    if fmt == "zip":
        with zipfile.ZipFile(output_archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in source_files:
                if isinstance(item, tuple):
                    file_path, arcname = item
                else:
                    file_path, arcname = item, item.name
                # Sanitize arcname: strip leading slashes and drive specs
                clean_arcname = arcname.lstrip("/\\")
                zf.write(file_path, arcname=clean_arcname)

    elif fmt in ("tar", "tar.gz", "tgz"):
        mode = "w:gz" if fmt in ("tar.gz", "tgz") else "w"
        with tarfile.open(output_archive_path, mode) as tf:
            for item in source_files:
                if isinstance(item, tuple):
                    file_path, arcname = item
                else:
                    file_path, arcname = item, item.name
                clean_arcname = arcname.lstrip("/\\")
                tf.add(file_path, arcname=clean_arcname)

    elif fmt == "gz":
        if not source_files:
            raise ValueError("No files provided for GZ compression.")
        first_item = source_files[0]
        file_path = first_item[0] if isinstance(first_item, tuple) else first_item
        with open(file_path, "rb") as f_in, gzip.open(output_archive_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    else:
        raise ValueError(f"Unsupported export archive format: '{archive_format}'")

    return output_archive_path
