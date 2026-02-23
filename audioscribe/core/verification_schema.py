# audioscribe/core/verification_schema.py

from __future__ import annotations

from typing import Any, Dict, List, Optional


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_FAILED = "failed"

ALLOWED_STATUS = {STATUS_OK, STATUS_WARNING, STATUS_FAILED}


def blank_verification(path: Optional[str]) -> Dict[str, Any]:
    """
    Canonical verification shape (same keys always).
    """
    return {
        "ok": False,
        "status": STATUS_FAILED,
        "path": path,
        "metrics": {
            "duration_s": None,
            "sample_rate_hz": None,
            "bitrate_kbps": None,
            "channels": None,
            "file_size_bytes": None,
        },
        "warnings": [],
        "errors": [],
    }


def normalize_verification(
    *,
    status: Optional[str],
    path: Optional[str],
    metrics: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
    errors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Produce canonical verification dict, forcing all keys to exist.
    """
    s = (status or STATUS_FAILED).strip().lower()
    if s not in ALLOWED_STATUS:
        s = STATUS_FAILED

    m = metrics or {}
    w = warnings or []
    e = errors or []

    result = blank_verification(path)

    result["status"] = s
    result["ok"] = (s != STATUS_FAILED)

    # Force metrics subkeys
    result["metrics"] = {
        "duration_s": m.get("duration_s"),
        "sample_rate_hz": m.get("sample_rate_hz"),
        "bitrate_kbps": m.get("bitrate_kbps"),
        "channels": m.get("channels"),
        "file_size_bytes": m.get("file_size_bytes"),
    }

    result["warnings"] = list(w)
    result["errors"] = list(e)

    return result