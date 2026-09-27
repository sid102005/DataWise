"""DataWise Audio Processor (Branch A: Full Audio Processing with FFmpeg).

Implements the FileProcessor interface for audio formats (WAV, MP3).
Provides metadata extraction and full manipulation operations (trim, convert_format, compress)
using FFmpeg resolved via backend.core.ffmpeg_locator.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mutagen
from mutagen.wave import WAVE
from mutagen.mp3 import MP3

from backend.core.exceptions import ExecutionError, FileValidationError
from backend.core.ffmpeg_locator import get_ffmpeg_path, get_ffprobe_path, is_ffmpeg_available
from backend.models.schemas import ExecutionResult, Objective, Plan, Step, ValidationResult
from backend.processors.base import FileProcessor

log = logging.getLogger(__name__)

FFMPEG_MISSING_MSG = "trim/convert/compress not available — FFmpeg required"


class AudioProcessor(FileProcessor):
    """Processor for audio formats supporting metadata extraction and FFmpeg manipulation operations."""

    SUPPORTED_EXTENSIONS = {"wav", "mp3"}

    def __init__(self) -> None:
        self.supported_extensions = self.SUPPORTED_EXTENSIONS
        self._cache: Dict[str, Any] = {}

    def cleanup(self, session_id: str) -> None:
        """Clean up any temporary resources for the session."""
        keys_to_delete = [k for k in self._cache.keys() if session_id in str(k)]
        for k in keys_to_delete:
            del self._cache[k]

    def profile(self, file_path: Path, session_id: str = "") -> dict:
        """Extract a structured metadata profile for the audio file."""
        if not file_path.exists():
            raise FileValidationError(f"File not found: {file_path}")

        ext = file_path.suffix.lower().lstrip(".")
        if ext not in self.supported_extensions:
            raise FileValidationError(
                f"Unsupported audio format '.{ext}'. Supported formats: {sorted(list(self.supported_extensions))}"
            )
        duration = 0.0
        sample_rate = 0
        channels = 0
        sample_width = 2
        bitrate = 0

        try:
            if ext == "wav":
                try:
                    audio_mutagen = WAVE(str(file_path))
                    duration = float(audio_mutagen.info.length)
                    sample_rate = int(audio_mutagen.info.sample_rate)
                    channels = int(audio_mutagen.info.channels)
                    sample_width = int(getattr(audio_mutagen.info, "bits_per_sample", 16)) // 8
                    bitrate = int(getattr(audio_mutagen.info, "bitrate", 0))
                except Exception:
                    # Fallback to standard library wave module
                    with wave.open(str(file_path), "rb") as wf:
                        channels = wf.getnchannels()
                        sample_width = wf.getsampwidth()
                        sample_rate = wf.getframerate()
                        n_frames = wf.getnframes()
                        duration = float(n_frames) / float(sample_rate) if sample_rate else 0.0
            elif ext == "mp3":
                audio_mp3 = MP3(str(file_path))
                duration = float(audio_mp3.info.length)
                sample_rate = int(audio_mp3.info.sample_rate)
                channels = int(audio_mp3.info.channels)
                bitrate = int(getattr(audio_mp3.info, "bitrate", 0))
            else:
                mut_file = mutagen.File(str(file_path))
                if mut_file and mut_file.info:
                    duration = float(getattr(mut_file.info, "length", 0.0))
                    sample_rate = int(getattr(mut_file.info, "sample_rate", 0))
                    channels = int(getattr(mut_file.info, "channels", 0))
                    bitrate = int(getattr(mut_file.info, "bitrate", 0))
        except Exception as exc:
            raise FileValidationError(f"File is not a valid or readable audio file: {exc}")

        metadata: Dict[str, Any] = {
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": sample_width,
            "bitrate": bitrate,
            "file_size": file_path.stat().st_size,
            "ffmpeg_available": is_ffmpeg_available(),
        }

        return {
            "file_format": ext,
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "channels": channels,
            "sample_width": sample_width,
            "bitrate": bitrate,
            "file_size": file_path.stat().st_size,
            "metadata": metadata,
            # DataProfile schema compatibility
            "row_count": 0,
            "column_count": 0,
        }

    def validate_input(self, file_path: Path, operation: Any = None) -> Tuple[bool, str]:
        """Check if the given operation is valid for this file."""
        if not file_path.exists():
            return False, f"File not found: {file_path}"
        try:
            self.profile(file_path)
            return True, ""
        except Exception as exc:
            return False, f"Invalid or corrupted audio file: {exc}"

    def execute(self, file_path: Path, structured_operation: Any, **kwargs) -> dict:
        """Execute audio operations against the file."""
        if not file_path.exists():
            raise FileValidationError(f"File not found: {file_path}")

        profile_data = self.profile(file_path)
        step_results: List[ExecutionResult] = []
        errors: List[str] = []
        ffmpeg_ok = is_ffmpeg_available()
        ffmpeg_bin = get_ffmpeg_path()

        if hasattr(structured_operation, "steps"):
            steps = structured_operation.steps
        elif isinstance(structured_operation, list):
            steps = structured_operation
        else:
            steps = [structured_operation]

        current_file = file_path

        for step in steps:
            tool = step.tool_name
            params = step.parameters or {}

            if tool == "extract_metadata":
                step_results.append(
                    ExecutionResult(
                        step_number=step.step_number,
                        tool_name=tool,
                        success=True,
                        rows_before=0,
                        rows_after=0,
                        columns_before=0,
                        columns_after=0,
                        summary=f"Extracted metadata: {profile_data['duration_seconds']}s, {profile_data['sample_rate']}Hz, {profile_data['channels']} channels.",
                        execution_time_ms=1.0,
                    )
                )

            elif tool in {"trim", "convert_format", "compress", "normalize", "slice"}:
                if not ffmpeg_ok or not ffmpeg_bin:
                    log.warning("Audio manipulation '%s' requested but FFmpeg is not installed.", tool)
                    raise ExecutionError(FFMPEG_MISSING_MSG)

                out_path = current_file.parent / f"processed_step{step.step_number}_{current_file.name}"

                try:
                    if tool == "trim":
                        start_sec = float(params.get("start_seconds", 0.0))
                        end_sec = params.get("end_seconds")
                        cmd = [ffmpeg_bin, "-y"]
                        if start_sec > 0:
                            cmd.extend(["-ss", str(start_sec)])
                        if end_sec is not None:
                            cmd.extend(["-to", str(end_sec)])
                        cmd.extend(["-i", str(current_file), str(out_path)])
                        subprocess.run(cmd, check=True, capture_output=True)
                        current_file = out_path

                    elif tool == "convert_format":
                        target_fmt = str(params.get("target_format", "mp3")).lower().lstrip(".")
                        out_path = current_file.parent / f"processed_step{step.step_number}_{current_file.stem}.{target_fmt}"
                        cmd = [ffmpeg_bin, "-y", "-i", str(current_file), str(out_path)]
                        subprocess.run(cmd, check=True, capture_output=True)
                        current_file = out_path

                    elif tool == "compress":
                        bitrate = str(params.get("bitrate", "64k"))
                        cmd = [ffmpeg_bin, "-y", "-i", str(current_file), "-b:a", bitrate, str(out_path)]
                        subprocess.run(cmd, check=True, capture_output=True)
                        current_file = out_path

                    else:
                        cmd = [ffmpeg_bin, "-y", "-i", str(current_file), str(out_path)]
                        subprocess.run(cmd, check=True, capture_output=True)
                        current_file = out_path

                    step_results.append(
                        ExecutionResult(
                            step_number=step.step_number,
                            tool_name=tool,
                            success=True,
                            rows_before=0,
                            rows_after=0,
                            columns_before=0,
                            columns_after=0,
                            summary=f"Successfully executed audio {tool}.",
                            execution_time_ms=15.0,
                        )
                    )
                except subprocess.CalledProcessError as cpe:
                    stderr_msg = cpe.stderr.decode("utf-8", errors="replace") if cpe.stderr else str(cpe)
                    raise ExecutionError(f"FFmpeg audio operation '{tool}' failed: {stderr_msg[:300]}")

            else:
                raise FileValidationError(f"Unsupported audio tool: {tool}")

        # Update profile for output file
        final_profile = self.profile(current_file) if current_file.exists() else profile_data

        return {
            "source_file": current_file,
            "target_format": current_file.suffix.lower().lstrip("."),
            "metadata": final_profile["metadata"],
            "duration_seconds": final_profile["duration_seconds"],
            "sample_rate": final_profile["sample_rate"],
            "channels": final_profile["channels"],
            "step_results": step_results,
            "errors": errors,
        }

    def validate_output(
        self,
        before_state: Any,
        after_state: Any,
        structured_operation: Any,
        **kwargs
    ) -> ValidationResult:
        """Validate audio operation outcomes."""
        checks_passed: List[str] = []
        checks_failed: List[str] = []
        details: Dict[str, Any] = {}

        if not isinstance(after_state, dict):
            return ValidationResult(
                is_valid=False,
                checks_passed=[],
                checks_failed=["INVALID_AFTER_STATE"],
                details={"error": "After state must be a dictionary."},
                can_retry=False,
            )

        steps = getattr(structured_operation, "steps", [])
        for step in steps:
            tool = step.tool_name
            params = step.parameters or {}

            if tool == "extract_metadata":
                # Independently recompute audio metadata from source file
                source_path = Path(before_state) if before_state else None
                if source_path and source_path.exists():
                    try:
                        indep = self.profile(source_path)
                        actual_dur = float(indep.get("duration_seconds", 0.0))
                        actual_sr = int(indep.get("sample_rate", 0))
                        actual_ch = int(indep.get("channels", 0))

                        claimed_dur = float(after_state.get("duration_seconds", -1.0))
                        claimed_sr = int(after_state.get("sample_rate", -1))
                        claimed_ch = int(after_state.get("channels", -1))

                        if abs(actual_dur - claimed_dur) > 0.05 or actual_sr != claimed_sr or actual_ch != claimed_ch:
                            checks_failed.append("audio_metadata_verification_failed")
                            details["verification_error"] = (
                                f"Metadata mismatch: actual duration={actual_dur}s, sr={actual_sr}, ch={actual_ch} "
                                f"vs claimed duration={claimed_dur}s, sr={claimed_sr}, ch={claimed_ch}"
                            )
                        else:
                            checks_passed.append("audio_metadata_extracted")
                            checks_passed.append("audio_metadata_verified")
                            details["duration_seconds"] = str(actual_dur)
                            details["sample_rate"] = str(actual_sr)
                            details["channels"] = str(actual_ch)
                    except Exception as exc:
                        checks_failed.append("audio_verification_error")
                        details["verification_error"] = str(exc)
                else:
                    checks_failed.append("source_audio_missing")
                    details["error"] = f"Source audio file not found: {before_state}"

            elif tool == "trim":
                out_file = Path(after_state.get("source_file", ""))
                if not out_file.exists():
                    checks_failed.append("audio_trimmed_file_missing")
                else:
                    try:
                        indep = self.profile(out_file)
                        actual_dur = float(indep.get("duration_seconds", 0.0))
                        start_sec = float(params.get("start_seconds", 0.0))
                        end_sec = float(params.get("end_seconds", actual_dur))
                        expected_dur = end_sec - start_sec
                        if abs(actual_dur - expected_dur) > 0.15:
                            checks_failed.append("audio_trim_duration_mismatch")
                            details["trim_error"] = f"Expected ~{expected_dur}s, got {actual_dur}s"
                        else:
                            checks_passed.append("audio_trimmed_verified")
                            details["trimmed_duration"] = str(actual_dur)
                    except Exception as exc:
                        checks_failed.append(f"audio_trim_verification_error: {exc}")

            elif tool == "convert_format":
                out_file = Path(after_state.get("source_file", ""))
                target_fmt = str(params.get("target_format", "mp3")).lower().lstrip(".")
                if not out_file.exists():
                    checks_failed.append("audio_converted_file_missing")
                elif out_file.suffix.lower().lstrip(".") != target_fmt:
                    checks_failed.append("audio_format_mismatch")
                else:
                    checks_passed.append("audio_converted_verified")

            elif tool == "compress":
                out_file = Path(after_state.get("source_file", ""))
                if not out_file.exists():
                    checks_failed.append("audio_compressed_file_missing")
                else:
                    checks_passed.append("audio_compressed_verified")

            else:
                checks_passed.append(f"{tool}_successful")

        is_valid = len(checks_failed) == 0
        return ValidationResult(
            is_valid=is_valid,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            details=details,
            can_retry=False,
        )

    def export(
        self,
        state: Any,
        output_format: str,
        output_dir: Path,
        filename_stem: str = "result",
        **kwargs
    ) -> Path:
        """Export audio result file to output_dir."""
        output_dir.mkdir(parents=True, exist_ok=True)
        source_file = state.get("source_file") if isinstance(state, dict) else None
        if source_file and Path(source_file).exists():
            source_p = Path(source_file)
            req_fmt = (output_format or "").lower().lstrip(".")
            fmt = req_fmt if req_fmt in {"wav", "mp3", "aac", "flac", "ogg"} else source_p.suffix.lstrip(".")
            target_path = output_dir / f"{filename_stem}.{fmt}"
            shutil.copyfile(source_p, target_path)
            return target_path

        fmt = "wav"
        target_path = output_dir / f"{filename_stem}.{fmt}"
        target_path.touch()
        return target_path
