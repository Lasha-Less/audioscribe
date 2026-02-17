from __future__ import annotations

import json
import subprocess
from pathlib import Path

from audioscribe.core.models import (
    VerificationMetrics,
    VerificationResult,
    VerificationStatus,
)


def verify_audio(mp3_path: str | Path) -> VerificationResult:
    """
    Verifies basic technical properties of an audio file using ffprobe.

    Extracts duration, bitrate, sample rate, channels and codec.
    Returns a structured VerificationResult.
    """
    mp3_path = Path(mp3_path)

    if not mp3_path.exists():
        return VerificationResult(
            status=VerificationStatus.FAILED,
            errors=[f"File not found: {mp3_path}"],
        )

    cmd = [
        "ffprobe",
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(mp3_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except Exception as e:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            errors=[f"ffprobe execution failed: {e!r}"],
        )

    if result.returncode != 0:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            errors=[result.stderr.strip() or "ffprobe returned error"],
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return VerificationResult(
            status=VerificationStatus.FAILED,
            errors=["Invalid JSON returned from ffprobe"],
        )

    format_info = data.get("format", {})
    streams = data.get("streams", [])

    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"),
        {},
    )

    duration = float(format_info.get("duration", 0)) if format_info.get("duration") else None
    bitrate = int(format_info.get("bit_rate", 0)) // 1000 if format_info.get("bit_rate") else None
    sample_rate = int(audio_stream.get("sample_rate", 0)) if audio_stream.get("sample_rate") else None
    channels = int(audio_stream.get("channels", 0)) if audio_stream.get("channels") else None
    codec = audio_stream.get("codec_name")

    metrics = VerificationMetrics(
        duration_s=duration,
        bitrate_kbps=bitrate,
        sample_rate_hz=sample_rate,
        channels=channels,
        codec=codec,
        file_size_bytes=int(format_info.get("size", 0)) if format_info.get("size") else None,
    )

    # Quality rules (Option A):
    warnings: list[str] = []
    errors: list[str] = []

    # Rule A1: duration must be meaningful (avoid bogus/empty downloads)
    if duration is None or duration <= 0:
        errors.append("Invalid or zero duration")
    elif duration < 5.0:
        errors.append(f"Duration too short: {duration:.2f}s < 5.00s")

    # Rule A2: bitrate quality warning (do not fail)
    if bitrate is not None and bitrate < 96:
        warnings.append(f"Low bitrate: {bitrate} kbps < 96 kbps")

    # Decide overall status
    if errors:
        status = VerificationStatus.FAILED
    elif warnings:
        status = VerificationStatus.WARNING
    else:
        status = VerificationStatus.OK

    return VerificationResult(
        status=status,
        metrics=metrics,
        warnings=warnings,
        errors=errors,
    )

