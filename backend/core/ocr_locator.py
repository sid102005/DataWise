"""Locate the Tesseract OCR binary and configure pytesseract.

Resolution order:
1. Explicit ``TESSERACT_BINARY`` / ``TESSERACT_CMD`` env override
2. ``shutil.which("tesseract")`` on PATH
3. Common Windows install paths (Program Files, local AppData)
4. WinGet package probe under LOCALAPPDATA\\Microsoft\\WinGet\\Packages
"""

from __future__ import annotations

import glob
import os
import shutil
import sys
from pathlib import Path


def get_tesseract_path() -> str | None:
    """Return absolute path to tesseract executable, or None if not found."""
    for env_var in ("TESSERACT_BINARY", "TESSERACT_CMD"):
        env_path = os.environ.get(env_var)
        if env_path and Path(env_path).is_file():
            return str(Path(env_path).resolve())

    found = shutil.which("tesseract")
    if found and Path(found).is_file():
        return str(Path(found).resolve())

    if sys.platform == "win32":
        candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
        ]
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            candidates.append(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
            pattern = os.path.join(
                local,
                "Microsoft",
                "WinGet",
                "Packages",
                "UB-Mannheim.TesseractOCR*",
                "**",
                "tesseract.exe",
            )
            for m in glob.glob(pattern, recursive=True):
                candidates.append(Path(m))

        for cand in candidates:
            if cand.is_file():
                return str(cand.resolve())

        # User PATH from registry (WinGet sometimes updates this without refreshing the shell)
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment")
            user_path, _ = winreg.QueryValueEx(key, "Path")
            for entry in user_path.split(";"):
                entry = entry.strip()
                if not entry:
                    continue
                candidate = Path(os.path.expandvars(entry)) / "tesseract.exe"
                if candidate.is_file():
                    return str(candidate.resolve())
        except Exception:
            pass

    return None


def is_tesseract_available() -> bool:
    return get_tesseract_path() is not None


def configure_pytesseract() -> str:
    """Import pytesseract, point it at the located binary, return the binary path.

    Raises:
        RuntimeError: if pytesseract package or Tesseract binary is missing.
    """
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires the pytesseract package. Install with: pip install pytesseract"
        ) from exc

    cmd = get_tesseract_path()
    if not cmd:
        raise RuntimeError(
            "OCR requires the Tesseract binary. Install it "
            "(e.g. `winget install UB-Mannheim.TesseractOCR`) and ensure it is on PATH, "
            "or set TESSERACT_BINARY to the full path of tesseract.exe."
        )

    pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


def ocr_pil_image(image) -> str:
    """Run OCR on a Pillow Image and return extracted text."""
    configure_pytesseract()
    import pytesseract

    text = pytesseract.image_to_string(image)
    return (text or "").strip()
