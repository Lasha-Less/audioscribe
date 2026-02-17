from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4
from urllib.parse import urlparse, parse_qs


@dataclass(frozen=True)
class Job:
    job_id: str
    urls: list[str]


# In-memory placeholder store (slice-safe: no DB yet)
_JOBS: dict[str, Job] = {}


def create_job(urls: Iterable[str]) -> dict:
    """
    Create a job for ingesting a set of URLs.
    Placeholder implementation: stores job in memory only.
    """
    url_list = [u.strip() for u in urls if str(u).strip()]
    job_id = str(uuid4())

    _JOBS[job_id] = Job(job_id=job_id, urls=url_list)

    return {
        "ok": True,
        "message": "job created (placeholder)",
        "job_id": job_id,
        "count": len(url_list),
    }


def _extract_youtube_id(url: str) -> str | None:
    """
    Best-effort extraction of YouTube video id from common URL formats.
    """
    try:
        u = urlparse(url)
        qs = parse_qs(u.query)
        if "v" in qs and qs["v"]:
            return qs["v"][0]
        # youtu.be/<id>
        if u.netloc.endswith("youtu.be"):
            vid = u.path.strip("/").split("/")[0]
            return vid or None
    except Exception:
        return None
    return None


def process_job(job_id: str) -> dict:
    """
    Process a job end-to-end.
    Minimal real implementation: downloads MP3 for the first URL via yt-dlp,
    then verifies the produced audio via ffprobe (JSON-serializable result).
    """
    job = _JOBS.get(job_id)
    if not job:
        return {"ok": False, "message": "job not found", "job_id": job_id}

    if not job.urls:
        return {"ok": False, "message": "no urls in job", "job_id": job_id}

    url = job.urls[0]

    # Save to repo-root /outputs (same idea you already used)
    out_dir = Path("outputs")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Output template -> produces: outputs/<title> [<id>].mp3
    out_template = str(out_dir / "%(title)s [%(id)s].%(ext)s")

    cmd = [
        "yt-dlp",
        "--windows-filenames",
        "--extractor-args", "youtube:player_client=android",
        "-x",
        "--audio-format", "mp3",
        "--print", "after_move:filepath",
        "-o", out_template,
        url,
    ]

    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        return {
            "ok": False,
            "message": "yt-dlp not found. Is it installed in this venv?",
            "job_id": job_id,
        }
    except subprocess.CalledProcessError as e:
        return {
            "ok": False,
            "message": "yt-dlp failed",
            "job_id": job_id,
            "stderr": (e.stderr or "")[-800:],  # last part only
        }

    # MP3 should exist now; yt-dlp prints the final filepath via after_move:filepath
    raw_out = (completed.stdout or "").strip()
    mp3_path = raw_out.splitlines()[-1].strip() if raw_out else ""

    # yt-dlp sometimes prints quotes around the filepath on Windows
    if mp3_path.startswith('"') and mp3_path.endswith('"'):
        mp3_path = mp3_path[1:-1].strip()

    mp3_exists = False
    mp3_path_obj = None

    if mp3_path:
        mp3_path_obj = Path(mp3_path)

        if not mp3_path_obj.is_absolute():
            mp3_path_obj = (Path.cwd() / mp3_path_obj).resolve()
            mp3_path = str(mp3_path_obj)

        mp3_exists = mp3_path_obj.exists()

    # Since our output template always contains "[<video_id>]", we can locate the real file by id.
    # Fallback: locate the real file by video id in filename
    if not mp3_exists:
        video_id = _extract_youtube_id(url)
        if video_id:
            needle = f"[{video_id}]"
            candidates = sorted(
                (p for p in out_dir.glob("*.mp3") if needle in p.name),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                mp3_path_obj = candidates[0]
                mp3_path = str(mp3_path_obj)
                mp3_exists = True

    debug = None
    if not mp3_exists:
        debug = {
            "stdout_tail": (completed.stdout or "")[-400:],
            "stderr_tail": (completed.stderr or "")[-400:],
        }

    verification_payload = None
    if mp3_exists:
        from audioscribe.core.verify_audio import verify_audio  # local import keeps startup simple
        verification = verify_audio(mp3_path)

        # JSON-serializable structure
        verification_payload = {
            "status": verification.status.value,
            "ok": verification.ok,
            "metrics": {
                "duration_s": verification.metrics.duration_s,
                "file_size_bytes": verification.metrics.file_size_bytes,
                "bitrate_kbps": verification.metrics.bitrate_kbps,
                "sample_rate_hz": verification.metrics.sample_rate_hz,
                "channels": verification.metrics.channels,
                "codec": verification.metrics.codec,
            },
            "warnings": verification.warnings,
            "errors": verification.errors,
        }

    return {
        "ok": True,
        "message": "downloaded mp3 (minimal)",
        "job_id": job_id,
        "url": url,
        "mp3_path": mp3_path,
        "mp3_exists": mp3_exists,
        "verification": verification_payload,
        "debug": debug,
    }



def get_job_status(job_id: str) -> dict:
    """
    Return job status.
    Placeholder implementation: only indicates existence for now.
    """
    exists = job_id in _JOBS
    return {
        "ok": True,
        "message": "status placeholder",
        "job_id": job_id,
        "exists": exists,
    }
