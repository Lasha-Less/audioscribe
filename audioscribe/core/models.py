from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VerificationStatus(str, Enum):
    """
        High-level verification outcome.

        OK       -> file passed all checks
        WARNING  -> file usable but quality issues detected
        FAILED   -> file invalid or corrupted
    """
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class VerificationMetrics:
    """
        Technical properties extracted from the audio file via ffprobe.
        All fields are optional because ffprobe may omit certain values.
    """
    duration_s: float | None = None
    file_size_bytes: int | None = None
    bitrate_kbps: int | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    codec: str | None = None


@dataclass(frozen=True)
class VerificationResult:
    """
        Result object returned by verify_audio().

        - status: overall outcome
        - metrics: extracted technical properties
        - warnings: non-fatal quality issues
        - errors: fatal validation failures
    """
    status: VerificationStatus
    metrics: VerificationMetrics = field(default_factory=VerificationMetrics)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """
            Convenience flag indicating successful verification.
        """
        return self.status == VerificationStatus.OK
