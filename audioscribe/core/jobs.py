from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4


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


def process_job(job_id: str) -> dict:
    """
    Process a job end-to-end.
    Minimal real implementation: downloads MP3 for the first URL via yt-dlp.
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

    # Output template -> produces: outputs/<job_id>.mp3 (or with title if you want later)
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

    # MP3 should exist now at outputs/<job_id>.mp3
    mp3_path = (completed.stdout or "").strip().splitlines()[-1] if (completed.stdout or "").strip() else ""
    exists = bool(mp3_path) and Path(mp3_path).exists()

    return {
        "ok": True,
        "message": "downloaded mp3 (minimal)",
        "job_id": job_id,
        "url": url,
        "mp3_path": mp3_path,
        "mp3_exists": exists,
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
