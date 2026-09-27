"""DataWise File Detection Layer.

Detects file categories using both extensions and magic signatures.
"""

from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class FileCategory(str, Enum):
    """Broad categories for file routing."""
    TABULAR = "tabular"
    DOCUMENT = "document"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    PRESENTATION = "presentation"
    UNKNOWN = "unknown"


class FileDetectionResult(BaseModel):
    filename: str
    extension: str
    mime_type: str
    magic_signature_category: FileCategory
    detected_category: FileCategory
    confidence: float


# Common magic byte signatures
MAGIC_SIGNATURES = {
    # Archives (ZIP also covers XLSX, DOCX, PPTX which are zip-based)
    b"PK\x03\x04": FileCategory.ARCHIVE,
    b"PK\x05\x06": FileCategory.ARCHIVE,  # Empty or multi-segment ZIP
    b"\x1f\x8b": FileCategory.ARCHIVE,  # GZIP
    # PDF
    b"%PDF": FileCategory.DOCUMENT,
    # Images
    b"\xff\xd8\xff": FileCategory.IMAGE,  # JPEG (FFD8FF)
    b"\x89PNG": FileCategory.IMAGE,  # PNG (89504E47)
    b"GIF87a": FileCategory.IMAGE,  # GIF (474946...)
    b"GIF89a": FileCategory.IMAGE,
    b"GIF": FileCategory.IMAGE,
    b"BM": FileCategory.IMAGE,  # BMP (424D)
    b"II*\x00": FileCategory.IMAGE,  # TIFF little-endian (49492A00)
    b"MM\x00*": FileCategory.IMAGE,  # TIFF big-endian (4D4D002A)
}


# Extension mappings by FileCategory (without leading dots)
CATEGORY_EXTENSIONS: dict[FileCategory, list[str]] = {
    FileCategory.TABULAR: ["csv", "xlsx", "json"],
    FileCategory.DOCUMENT: ["pdf", "docx", "txt", "md"],
    FileCategory.IMAGE: ["jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "tif"],
    FileCategory.VIDEO: ["mp4", "mov", "avi", "mkv", "webm"],
    FileCategory.AUDIO: ["mp3", "wav"],
    FileCategory.ARCHIVE: ["zip", "tar", "gz"],
    FileCategory.PRESENTATION: ["pptx"],
}


def _get_extension_category(ext: str) -> FileCategory:
    clean_ext = ext.lower().lstrip(".")
    for category, extensions in CATEGORY_EXTENSIONS.items():
        if clean_ext in extensions:
            return category
    return FileCategory.UNKNOWN



def _sniff_magic_bytes(file_path: Path) -> Optional[FileCategory]:
    try:
        with open(file_path, "rb") as f:
            header = f.read(1024)
        for sig, category in MAGIC_SIGNATURES.items():
            if header.startswith(sig):
                return category
            
        # WEBP signature: RIFF at offset 0, WEBP at offset 8
        if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return FileCategory.IMAGE

        # WAV signature: RIFF at offset 0, WAVE at offset 8
        if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WAVE":
            return FileCategory.AUDIO

        # AVI signature: RIFF at offset 0, AVI at offset 8
        if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"AVI ":
            return FileCategory.VIDEO

        # MP4 / MOV / QuickTime signature: 'ftyp' at offset 4 or 'moov' at offset 4
        if len(header) >= 8 and (header[4:8] == b"ftyp" or header[4:8] == b"moov"):
            return FileCategory.VIDEO

        # MKV / WEBM signature: EBML container header (1A 45 DF A3)
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return FileCategory.VIDEO

        # MP3 signature: ID3 header or MPEG frame sync
        if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
            return FileCategory.AUDIO

        # TAR signature: 'ustar' or 'GNUt' at offset 257
        if len(header) >= 262 and (header[257:262] in (b"ustar", b"GNUt")):
            return FileCategory.ARCHIVE

        # JSON heuristic (starts with '{' or '[')
        if header.lstrip().startswith(b"{") or header.lstrip().startswith(b"["):
            return FileCategory.TABULAR
            
        # Text/CSV heuristic (mostly printable ascii/utf-8)
        try:
            text = header.decode("utf-8")
            if text.isprintable() or any(c in text for c in "\n\r\t"):
                return FileCategory.TABULAR
        except UnicodeDecodeError:
            pass
            
    except Exception:
        pass
        
    return None


def detect_file(file_path: Path | str, original_filename: str = "") -> FileDetectionResult:
    """Detect file category using extension and signature heuristics."""
    from backend.core.exceptions import FileValidationError
    
    p = Path(file_path)
    filename = original_filename or p.name
    ext = Path(filename).suffix.lower()
    
    if ext in {".doc", ".docm"}:
        raise FileValidationError(f"Legacy Word format ({ext}) detected but rejected (binary/macros not supported). Please use .docx.")
    
    ext_category = _get_extension_category(ext)
    magic_category = _sniff_magic_bytes(p) or FileCategory.UNKNOWN
    
    final_category = ext_category
    confidence = 0.5
    
    # If magic bytes found something, it generally overrides or refines extension.
    if magic_category != FileCategory.UNKNOWN:
        if magic_category == ext_category:
            confidence = 1.0
        else:
            # Special case: XLSX/DOCX/PPTX are zip archives. 
            if magic_category == FileCategory.ARCHIVE and ext_category in {FileCategory.TABULAR, FileCategory.DOCUMENT, FileCategory.PRESENTATION}:
                confidence = 0.9  # Trust the extension to differentiate zip-based formats
            elif magic_category == FileCategory.TABULAR and ext_category == FileCategory.DOCUMENT and ext in {".txt", ".md"}:
                # Text heuristics might flag plain text as tabular, but trust extension for txt/md
                final_category = FileCategory.DOCUMENT
                confidence = 0.8
            else:
                # Magic bytes disagree with extension
                final_category = magic_category
                confidence = 0.8
    else:
        # Relied solely on extension
        if ext_category == FileCategory.IMAGE:
            # An image extension with no valid image magic signature is not trusted as an image
            final_category = FileCategory.UNKNOWN
            confidence = 0.2
        else:
            confidence = 0.4
        
    # Mime mapping (rough mapping for the result object)
    mime_type = "application/octet-stream"
    if ext == ".csv": mime_type = "text/csv"
    elif ext == ".xlsx": mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif ext == ".json": mime_type = "application/json"
    elif ext == ".pdf": mime_type = "application/pdf"
    elif ext == ".docx": mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext in {".txt", ".md"}: mime_type = "text/plain"
    elif ext in {".jpg", ".jpeg"}: mime_type = "image/jpeg"
    elif ext == ".png": mime_type = "image/png"
    elif ext == ".gif": mime_type = "image/gif"
    elif ext == ".bmp": mime_type = "image/bmp"
    elif ext == ".webp": mime_type = "image/webp"
    elif ext in {".tiff", ".tif"}: mime_type = "image/tiff"
    elif ext == ".wav": mime_type = "audio/wav"
    elif ext == ".mp3": mime_type = "audio/mpeg"
    elif ext == ".mp4": mime_type = "video/mp4"
    elif ext == ".mov": mime_type = "video/quicktime"
    elif ext == ".avi": mime_type = "video/x-msvideo"
    elif ext == ".mkv": mime_type = "video/x-matroska"
    elif ext == ".webm": mime_type = "video/webm"
    elif ext == ".zip": mime_type = "application/zip"
    elif ext in {".tar", ".tgz"}: mime_type = "application/x-tar"
    elif ext == ".gz": mime_type = "application/gzip"
    
    return FileDetectionResult(
        filename=filename,
        extension=ext,
        mime_type=mime_type,
        magic_signature_category=magic_category,
        detected_category=final_category,
        confidence=confidence
    )
