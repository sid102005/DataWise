"""DataWise Global Configuration and Path Utilities."""

from __future__ import annotations

import os
from pathlib import Path

# Base repository directory
REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env_file(env_path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from `.env` into os.environ (no overwrite)."""
    path = env_path or (REPO_ROOT / ".env")
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        pass


# Load project .env early so FFMPEG_BINARY / TESSERACT_BINARY / API keys are visible
load_env_file()

# Workspace directories for session-isolated file storage
WORKSPACE_DIR = REPO_ROOT / "workspace"
SESSIONS_DIR = WORKSPACE_DIR / "sessions"

# Application-level limits removed per Phase 9 v2 expansion.
# Real infrastructure limits (RAM, disk, browser upload size) still apply.

# Supported file formats
SUPPORTED_EXTENSIONS = {
    ".csv", ".xlsx", ".json",  # Tabular
    ".pdf", ".docx", ".txt", ".md",  # Document
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",  # Image
    ".mp3", ".wav",  # Audio
    ".mp4", ".mov", ".avi", ".mkv", ".webm",  # Video
    ".zip", ".tar", ".gz", ".tgz",  # Archive
}

# FFmpeg and FFprobe locator functions (path-independent resolution)
from backend.core.ffmpeg_locator import (
    get_ffmpeg_path,
    get_ffprobe_path,
    is_ffmpeg_available,
    is_ffprobe_available,
)


def ensure_workspace_directories(base_dir: Path | None = None) -> Path:
    """Ensure workspace and session storage directories exist on disk.

    Args:
        base_dir: Optional override directory (primarily for testing).

    Returns:
        Path to the validated sessions directory.
    """
    target_sessions = (base_dir / "sessions") if base_dir else SESSIONS_DIR
    target_sessions.mkdir(parents=True, exist_ok=True)
    return target_sessions
