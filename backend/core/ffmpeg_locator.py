"""Path-independent resolution strategy for FFmpeg and FFprobe binaries.

Resolution order:
1. Standard system PATH via shutil.which("ffmpeg") / shutil.which("ffprobe")
2. Explicit environment override via FFMPEG_BINARY / FFPROBE_BINARY
3. Well-known WinGet portable-install pattern on Windows:
   %LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*\\**\\bin\\ffmpeg.exe
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path


def _resolve_binary(name: str, env_var: str) -> str | None:
    # 1. System PATH
    found = shutil.which(name)
    if found and Path(found).is_file():
        return str(Path(found).resolve())

    # 2. Environment variable override
    env_path = os.environ.get(env_var)
    if env_path and Path(env_path).is_file():
        return str(Path(env_path).resolve())

    # 3. Windows WinGet package probe
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            pattern = os.path.join(
                local_app_data,
                "Microsoft",
                "WinGet",
                "Packages",
                "Gyan.FFmpeg_*",
                "**",
                f"{name}.exe",
            )
            matches = glob.glob(pattern, recursive=True)
            for m in matches:
                p = Path(m)
                if p.is_file() and os.access(str(p), os.X_OK):
                    return str(p.resolve())

            # Check registry User PATH as fallback probe
            try:
                import winreg

                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
                user_path, _ = winreg.QueryValueEx(key, "Path")
                for entry in user_path.split(";"):
                    entry = entry.strip()
                    if entry:
                        candidate = Path(os.path.expandvars(entry)) / f"{name}.exe"
                        if candidate.is_file() and os.access(str(candidate), os.X_OK):
                            return str(candidate.resolve())
            except Exception:
                pass

    return None


def get_ffmpeg_path() -> str | None:
    """Return absolute path to usable ffmpeg executable, or None."""
    return _resolve_binary("ffmpeg", "FFMPEG_BINARY")


def get_ffprobe_path() -> str | None:
    """Return absolute path to usable ffprobe executable, or None."""
    return _resolve_binary("ffprobe", "FFPROBE_BINARY")


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg executable is available on the system."""
    return get_ffmpeg_path() is not None


def is_ffprobe_available() -> bool:
    """Check if ffprobe executable is available on the system."""
    return get_ffprobe_path() is not None
